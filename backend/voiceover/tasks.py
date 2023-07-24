from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail
from celery.schedules import crontab
from datetime import datetime
from rest_framework.response import Response
from rest_framework import status
from .utils import integrate_audio_with_video, uploadToBlobStorage
from voiceover.models import VoiceOver
from task.models import Task
import os
import logging
from config import (
    storage_account_key,
    connection_string,
    container_name,
)


@shared_task()
def celery_integration(file_name, voice_over_obj_id, video, task_id):
    logging.info("Starting Async Celery Integration....")
    voice_over_obj = VoiceOver.objects.filter(id=voice_over_obj_id).first()
    task = Task.objects.filter(id=task_id).first()
    integrate_audio_with_video(file_name, voice_over_obj, voice_over_obj.video)
    if not os.path.isfile(file_name + ".mp4") or os.path.isfile(file_name + ".wav"):
        task.status = "FAILED"
        task.save()
        logging.info("Error in integrating audio and video")
    azure_url_video, azure_url_audio = uploadToBlobStorage(file_name, voice_over_obj)
    ts_status = "VOICEOVER_EDIT_COMPLETE"
    voice_over_obj.status = ts_status
    voice_over_obj.payload = {"payload": ""}
    voice_over_obj.azure_url = azure_url_video
    voice_over_obj.azure_url_audio = azure_url_audio
    voice_over_obj.save()
    task.status = "COMPLETE"
    task.save()
