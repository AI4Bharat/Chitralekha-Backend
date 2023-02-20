from transcript.utils.asr import make_asr_api_call
from transcript.models import Transcript
from task.models import Task
from io import StringIO

from celery import shared_task
import json
import webvtt
import datetime

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
def celery_asr_call(task_id):
    task_obj = Task.objects.get(pk=task_id)
    transcribed_data = make_asr_api_call(task_obj.video.url, task_obj.video.language)
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