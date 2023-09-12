from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail
from celery.schedules import crontab
from datetime import datetime
from rest_framework.response import Response
from rest_framework import status
from .utils import (
    integrate_audio_with_video,
    uploadToBlobStorage,
    download_from_azure_blob,
    upload_audio_to_azure_blob,
    send_audio_mail_to_user,
    add_bg_music,
)
from voiceover.models import VoiceOver
from task.models import Task
from users.models import User
import os
import logging
from config import (
    storage_account_key,
    connection_string,
    container_name,
)
from pydub import AudioSegment
from backend.celery import celery_app
import math
from moviepy.editor import VideoFileClip, AudioFileClip, concatenate_audioclips
import re


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
    task.status = "COMPLETE"
    voice_over_obj.save()
    task.save()


@shared_task()
def export_voiceover_async(task_id, export_type, user_id, bg_music):
    user = User.objects.get(pk=user_id)
    task = Task.objects.get(pk=task_id)
    voice_over = (
        VoiceOver.objects.filter(task__id=task_id)
        .filter(target_language=task.target_language)
        .filter(status="VOICEOVER_EDIT_COMPLETE")
        .first()
    )
    if voice_over is not None:
        download_from_azure_blob(str(voice_over.azure_url_audio))
        logging.info("Downloaded audio from Azure Blob %s", voice_over.azure_url_audio)
        file_path = voice_over.azure_url_audio.split("/")[-1]
        video_link = task.video.url
        if bg_music == "true":
            file_path_music = add_bg_music(
                os.path.join("temporary_video_audio_storage", file_path.split("/")[-1]),
                video_link,
            )
            AudioSegment.from_file(file_path_music).export(
                file_path.split("/")[-1].replace(".flac", "") + "." + export_type,
                format=export_type,
            )
        else:
            AudioSegment.from_file(file_path).export(
                file_path.split("/")[-1].replace(".flac", "") + "." + export_type,
                format=export_type,
            )
        logging.info("Uploading audio to Azure Blob %s", voice_over.azure_url_audio)
        azure_url_audio = upload_audio_to_azure_blob(
            file_path, export_type, export=True
        )
        try:
            os.remove(file_path)
            os.remove(file_path.split("/")[-1].replace(".flac", "") + "." + export_type)
        except:
            logging.info("Error in removing files")
        send_audio_mail_to_user(task, azure_url_audio, user)
    else:
        logging.info("Error in exporting %s", str(task_id))
