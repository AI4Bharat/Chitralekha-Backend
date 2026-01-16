from transcript.utils.asr import make_asr_api_call
from transcript.models import Transcript
from task.models import Task
from io import StringIO
from celery import shared_task
from backend.celery import celery_app
import json
import webvtt
import datetime
from voiceover.models import VoiceOver
from voiceover.utils import (
    generate_tts_output,
    send_mail_to_user,
    process_translation_payload,
)
from translation.models import Translation
import pysrt
import logging
from translation.utils import generate_translation_payload
from rest_framework.response import Response


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


def convert_srt_to_payload(srt_content, video=None, is_multi_speaker=False):
    """
    Convert SRT content to payload format.
    Handles speaker tags in format "S1:", "S2:", etc. if multi-speaker project.
    
    Args:
        srt_content: String content of SRT file
        video: Video object to validate speaker names (optional)
        is_multi_speaker: Boolean indicating if project has multiple speakers
        
    Returns:
        Dict with payload and potential error message
    """
    import re
    
    subs = pysrt.from_string(srt_content)
    sentences_list = []
    speaker_pattern = re.compile(r'^([A-Za-z0-9]+):\s*(.*)$', re.MULTILINE)
    found_speakers = set()
    
    for srt_line in subs:
        start_time = srt_line.start.to_time().strftime("%H:%M:%S.%f")[:-3]
        end_time = srt_line.end.to_time().strftime("%H:%M:%S.%f")[:-3]
        
        text = srt_line.text.strip()
        speaker_name = None
        
        # Check for speaker tag if multi-speaker project
        if is_multi_speaker and text:
            # Check first line of text for speaker pattern
            lines = text.split('\n')
            first_line = lines[0]
            match = speaker_pattern.match(first_line)
            
            if match:
                speaker_name = match.group(1)  # Extract speaker name
                extracted_text = match.group(2)  # Extract text without speaker tag
                
                # If there are multiple lines, append remaining lines
                if len(lines) > 1:
                    remaining_lines = '\n'.join(lines[1:])
                    text = extracted_text + "\n" + remaining_lines
                else:
                    text = extracted_text
                
                found_speakers.add(speaker_name)
        
        entry = {
            "start_time": start_time,
            "end_time": end_time,
            "text": text,
            "unix_start_time": srt_line.start.ordinal / 1000.0,
            "unix_end_time": srt_line.end.ordinal / 1000.0,
        }
        
        # Add speaker_name only if present
        if speaker_name:
            entry["speaker_name"] = speaker_name
        
        sentences_list.append(entry)
    
    # Validate speaker names if video object is provided
    if is_multi_speaker and video and found_speakers:
        video_speakers = set()
        if video.speaker_info and isinstance(video.speaker_info, dict):
            # Assuming speaker_info is dict with speaker names as keys or has "speakers" key
            if "speakers" in video.speaker_info:
                video_speakers = set(video.speaker_info["speakers"].keys())
            else:
                video_speakers = set(video.speaker_info.keys())
        
        # Check if found speakers match video speakers
        if video_speakers and not found_speakers.issubset(video_speakers):
            invalid_speakers = found_speakers - video_speakers
            return {
                "error": True,
                "message": f"Speaker names in SRT file ({', '.join(invalid_speakers)}) do not match with speakers in video details ({', '.join(video_speakers)})"
            }
    
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


def convert_dhruva_payload_format(text):
    lines = text.strip().split("\n")
    data_list = []
    i = 0

    while i < len(lines):
        entry = {}
        start_time, end_time = lines[i + 1].split(" --> ")
        if i + 2 == len(lines):
            entry["text"] = ""
        else:
            entry["text"] = lines[i + 2]
        entry["start_time"] = start_time.replace(",", ".")
        entry["end_time"] = end_time.replace(",", ".")
        start_time = datetime.datetime.strptime(entry["start_time"], "%H:%M:%S.%f")
        unix_start_time = datetime.datetime.timestamp(start_time)
        end_time = datetime.datetime.strptime(entry["end_time"], "%H:%M:%S.%f")
        unix_end_time = datetime.datetime.timestamp(end_time)
        entry["unix_start_time"] = unix_start_time
        entry["unix_end_time"] = unix_end_time
        data_list.append(entry)
        i += 4
    return json.loads(json.dumps({"payload": data_list}))


@celery_app.task(queue="asr_tts")
def celery_tts_call(
    task_id, tts_input, target_language, translation, translation_id, empty_sentences
):
    logging.info("Calling TTS API for %s", str(task_id))
    task_obj = Task.objects.get(pk=task_id)
    translation_obj = (
        Translation.objects.filter(target_language=target_language)
        .filter(video=task_obj.video)
        .filter(status__in=["TRANSLATION_EDIT_COMPLETE", "TRANSLATION_REVIEW_COMPLETE"])
        .first()
    )
    logging.info("Generate TTS output ID %s", str(translation_obj.task.id))
    logging.info("Translation ID %s", str(translation_id))
    logging.info("Empty sentences %s", str(empty_sentences))
    voiceover_obj = VoiceOver.objects.filter(task=task_obj).first()
    if voiceover_obj is None:
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
        task_obj.status = "SELECTED_SOURCE"
        task_obj.save()
        logging.info("Payload generated for TTS API for %s", str(task_id))
        if "message" in tts_payload:
            task_obj.is_active = False
            task_obj.status = "FAILED"
            task_obj.save()
        try:
            send_mail_to_user(task_obj)
        except:
            logging.info("Error in sending mail")
    else:
        logging.info("VoiceOver obj already exists")


@celery_app.task(queue="ekstep_asr")
def celery_ekstep_asr_call(task_id):
    task_obj = Task.objects.get(pk=task_id)
    transcript_obj = Transcript.objects.filter(task=task_obj).first()
    if transcript_obj is None:
        transcribed_data = make_asr_api_call(
            task_obj.video.url, task_obj.video.language
        )
        if transcribed_data is not None:
            if task_obj.video.language == "en":
                task_obj = Task.objects.get(pk=task_id)
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
                data = convert_dhruva_payload_format(transcribed_data)
                task_obj = Task.objects.get(pk=task_id)
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


@celery_app.task(queue="asr_tts")
def celery_asr_call(task_id):
    task_obj = Task.objects.get(pk=task_id)
    transcript_obj = Transcript.objects.filter(task=task_obj).first()
    if transcript_obj is None:
        transcribed_data = make_asr_api_call(
            task_obj.video.url, task_obj.video.language
        )
        if transcribed_data is not None:
            if task_obj.video.language == "en":
                task_obj = Task.objects.get(pk=task_id)
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
                task_obj.status = "SELECTED_SOURCE"
                task_obj.save()
                transcript_obj.save()
                send_mail_to_user(task_obj)
            else:
                data = convert_dhruva_payload_format(transcribed_data)
                task_obj = Task.objects.get(pk=task_id)
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
            task_obj.status = "FAILED"
            task_obj.save()
    else:
        logging.info("Transcript already exists")


@celery_app.task(queue="nmt")
def celery_nmt_call(task_id):
    task_obj = Task.objects.get(pk=task_id)
    translation_obj = Translation.objects.filter(task=task_obj).first()
    source_type = "MACHINE_GENERATED"
    if translation_obj is not None and type(translation_obj.payload) != dict:
        payloads = generate_translation_payload(
            translation_obj.transcript,
            translation_obj.target_language,
            [source_type],
            task_obj.user.id,
        )
        if type(payloads[source_type]) == Response:
            task_obj.status = "FAILED"
            task_obj.is_active = False
            task_obj.save()
        else:
            if (
                type(translation_obj.payload) == dict
                and "speaker_info" in translation_obj.payload
            ):
                translation_obj.payload["payload"] = payloads[source_type]["payload"]
            else:
                translation_obj.payload = payloads[source_type]
            translation_obj.save()
            task_obj.status = "SELECTED_SOURCE"
            task_obj.is_active = True
            task_obj.save()
            send_mail_to_user(task_obj)
    else:
        logging.info("Translation already exists")


@celery_app.task(queue="nmt")
def celery_nmt_tts_call(task_id):
    task_obj = Task.objects.get(pk=task_id)
    if task_obj.status in ["POST_PROCESS", "COMPLETE"]:
        logging.info(f"Task {task_id} is already complete (status: {task_obj.status})")
        return
    translation_obj = Translation.objects.filter(task=task_obj).first()
    source_type = "MACHINE_GENERATED"
    if translation_obj is not None and type(translation_obj.payload) != dict:
        payloads = generate_translation_payload(
            translation_obj.transcript,
            translation_obj.target_language,
            [source_type],
            task_obj.user.id,
        )
        if type(payloads[source_type]) == Response:
            task_obj.status = "FAILED"
            task_obj.is_active = False
            task_obj.save()
            logging.info("Generating translation payload failed for %s", str(task_id))
            return
        else:
            if (
                type(translation_obj.payload) == dict
                and "speaker_info" in translation_obj.payload
            ):
                translation_obj.payload["payload"] = payloads[source_type]["payload"]
            else:
                translation_obj.payload = payloads[source_type]
            translation_obj.save()
            task_obj.status = "SELECTED_SOURCE"
            # task_obj.is_active = True
            task_obj.save()

    tts_payload = process_translation_payload(
        translation_obj, task_obj.target_language
    )
    if type(tts_payload) == dict and "message" in tts_payload.keys():
        message = tts_payload["message"]
        logging.info("Error from TTS API")
        logging.info(message)
        raise ValueError(message)
        voice_over_task.status = "FAILED"
        voice_over_task.save()
        # set_fail_for_translation_task(task)
        return message

    (
        tts_input,
        target_language,
        translation,
        translation_id,
        empty_sentences,
    ) = tts_payload

    generate_audio = task_obj.video.project_id.pre_generate_audio
    tts_payload = generate_tts_output(
        tts_input,
        target_language,
        translation,
        translation_obj,
        empty_sentences,
        generate_audio,
    )
    payloads = tts_payload

    existing_voiceover = VoiceOver.objects.filter(task=task_obj).first()

    print("Fetched voiceover", existing_voiceover)

    if existing_voiceover == None:
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
    else:
        existing_voiceover.payload = tts_payload
        existing_voiceover.translation = translation_obj
        existing_voiceover.save()
    task_obj.is_active = True
    task_obj.status = "SELECTED_SOURCE"
    task_obj.save()
    logging.info("Payload generated for TTS API for %s", str(task_id))
    if "message" in tts_payload:
        task_obj.is_active = False
        task_obj.status = "FAILED"
        task_obj.save()
    try:
        send_mail_to_user(task_obj)
    except:
        logging.info("Error in sending mail")