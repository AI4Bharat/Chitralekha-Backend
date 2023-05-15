from transcript.utils.asr import make_asr_api_call
from transcript.models import Transcript
from task.models import Task
from io import StringIO
from celery import shared_task
import json
import webvtt
import datetime
from voiceover.models import VoiceOver
from voiceover.utils import generate_tts_output, send_mail_to_user
from translation.models import Translation
import pysrt
import logging


def convert_vtt_to_payload(vtt_content):
    sentences_list = []
    for vtt_line in webvtt.read_buffer(StringIO(vtt_content)):
        start_time = datetime.datetime.strptime(vtt_line.start, "%H:%M:%S.%f")
        unix_start_time = datetime.datetime.timestamp(start_time)
        end_time = datetime.datetime.strptime(vtt_line.end, "%H:%M:%S.%f")
        unix_end_time = datetime.datetime.timestamp(end_time)

        sentences_list.append(
            {
                "start_time": vtt_line.start,
                "end_time": vtt_line.end,
                "text": vtt_line.text,
                "unix_start_time": unix_start_time,
                "unix_end_time": unix_end_time,
            }
        )
    return json.loads(json.dumps({"payload": sentences_list}))


def convert_srt_to_payload(srt_content):
    subs = pysrt.from_string(srt_content)
    sentences_list = []
    for srt_line in subs:
        start_time = datetime.datetime.fromtimestamp(srt_line.start.ordinal / 1000.0).strftime('%H:%M:%S.%f')
        end_time = datetime.datetime.fromtimestamp(srt_line.end.ordinal / 1000.0).strftime('%H:%M:%S.%f')

        sentences_list.append({
            "start_time": start_time,
            "end_time": end_time,
            "text": srt_line.text,
            "unix_start_time": srt_line.start.ordinal / 1000.0,
            "unix_end_time": srt_line.end.ordinal / 1000.0,
        })
    return json.loads(json.dumps({"payload": sentences_list}))


def convert_payload_format(data):
    sentences_list = []
    if "output" in data.keys():
        payload = data["output"]
    for vtt_line in webvtt.read_buffer(StringIO(payload)):
        start_time = datetime.datetime.strptime(vtt_line.start, "%H:%M:%S.%f")
        unix_start_time = datetime.datetime.timestamp(start_time)
        end_time = datetime.datetime.strptime(vtt_line.end, "%H:%M:%S.%f")
        unix_end_time = datetime.datetime.timestamp(end_time)

        sentences_list.append(
            {
                "start_time": vtt_line.start,
                "end_time": vtt_line.end,
                "text": vtt_line.text,
                "unix_start_time": unix_start_time,
                "unix_end_time": unix_end_time,
            }
        )
    return json.loads(json.dumps({"payload": sentences_list}))


@shared_task()
def celery_tts_call(
    task_id, tts_input, target_language, translation, translation_id, empty_sentences
):
    translation_obj = Translation.objects.get(id=translation_id)
    task_obj = Task.objects.get(pk=task_id)
    logging.info("Generate TTS output")
    tts_payload = generate_tts_output(
        tts_input, target_language, translation, translation_obj, empty_sentences
    )
    payloads = tts_payload
    voiceover_obj = VoiceOver(
        video=task_obj.video,
        user=task_obj.user,
        translation=translation_obj,
        payload=tts_payload,
        target_language=task_obj.target_language,
        task=task_obj,
        voice_over_type="MACHINE_GENERATED",
        status="VOICEOVER_SELECT_SOURCE",
    )
    voiceover_obj.save()
    task_obj.is_active = True
    task_obj.save()
    if "message" in tts_payload:
        task_obj.is_active = False
        task_obj.status = "FAILED"
        task_obj.save()
    send_mail_to_user(task_obj)


@shared_task()
def celery_asr_call(task_id):
    task_obj = Task.objects.get(pk=task_id)
    transcript_obj = Transcript.objects.filter(task=task_obj).first()
    if transcript_obj is None:
        transcribed_data = make_asr_api_call(
            task_obj.video.url, task_obj.video.language
        )
        if transcribed_data is not None:
            data = convert_payload_format(transcribed_data)
            transcript_obj = Transcript(
                video=task_obj.video,
                user=task_obj.user,
                payload=data,
                language=task_obj.video.language,
                task=task_obj,
                transcript_type="MACHINE_GENERATED",
                status="TRANSCRIPTION_SELECT_SOURCE",
            )
            task_obj.is_active = True
            task_obj.save()
            transcript_obj.save()
            send_mail_to_user(task_obj)
    else:
        logging.info("Transcript already exists")
