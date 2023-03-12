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


@shared_task(name="celery_integration")
def celery_integration(file_name, voice_over_obj_id, video, task_id):
    voice_over_obj = VoiceOver.objects.filter(id=voice_over_obj_id).first()
    task = Task.objects.filter(id=task_id).first()
    try:
        integrate_audio_with_video(file_name, voice_over_obj, voice_over_obj.video)
    except:
        logging.info("Error in integrating audio and video")
    azure_url = uploadToBlobStorage(file_name)
    ts_status = "VOICEOVER_EDIT_COMPLETE"
    voice_over_obj.status = ts_status
    voice_over_obj.payload = {"payload": ""}
    voice_over_obj.azure_url = azure_url
    voice_over_obj.save()
    task.status = "COMPLETE"
    task.save()
