import datetime
import io
from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail
from celery.schedules import crontab
from rest_framework.response import Response
from rest_framework import status
from .utils import (
    integrate_audio_with_video,
    uploadToBlobStorage,
    download_from_azure_blob,
    upload_audio_to_azure_blob,
    send_audio_mail_to_user,
    upload_zip_to_azure,
    send_audio_zip_mail_to_user,
)
from voiceover.models import VoiceOver
from task.models import Task, TRANSLATION_VOICEOVER_EDIT
from users.models import User
import os
import logging
from config import (
    storage_account_key,
    connection_string,
    container_name,
    bg_music_url,
)
from pydub import AudioSegment
from backend.celery import celery_app
import math
from moviepy.editor import VideoFileClip, AudioFileClip, concatenate_audioclips
import re
import json
import requests
import zipfile
from translation.models import Translation, TRANSLATION_EDIT_COMPLETE


@shared_task()
def celery_integration(file_name, voice_over_obj_id, video, task_id):
    logging.info("Starting Async Celery Integration....")
    voice_over_obj = VoiceOver.objects.filter(id=voice_over_obj_id).first()
    task = Task.objects.filter(id=task_id).first()

    if task.task_type == TRANSLATION_VOICEOVER_EDIT:
        final_tl = (
            Translation.objects.filter(task=task)
            .filter(status=TRANSLATION_EDIT_COMPLETE)
            .first()
        )
        if final_tl.payload != "" and final_tl.payload is not None:
            num_words = 0
            for idv_translation in final_tl.payload["payload"]:
                if "target_text" in idv_translation.keys():
                    cleaned_text = regex.sub(
                        r"[^\p{L}\s]", "", idv_translation["target_text"]
                    ).lower()  # for removing special characters
                    cleaned_text = regex.sub(
                        r"\s+", " ", cleaned_text
                    )  # for removing multiple blank spaces
                    num_words += len(cleaned_text.split(" "))
            final_tl.payload["word_count"] = num_words
        updated_payload = []
        for segment in voice_over_obj.payload["payload"].values():
            start_time = datetime.datetime.strptime(
                segment["start_time"], "%H:%M:%S.%f"
            )
            end_time = datetime.datetime.strptime(segment["end_time"], "%H:%M:%S.%f")
            unix_start_time = datetime.datetime.timestamp(start_time)
            unix_end_time = datetime.datetime.timestamp(end_time)
            target_text = segment["text"]
            target_text = segment["transcription_text"]

            updated_segment = {
                "start_time": segment["start_time"],
                "end_time": segment["end_time"],
                "target_text": segment["text"],
                "speaker_id": "",
                "unix_start_time": unix_start_time,
                "unix_end_time": unix_end_time,
                "text": segment["transcription_text"],
            }
            updated_payload.append(updated_segment)
        final_tl.payload["payload"] = updated_payload
        final_tl.save()

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
            json_data = json.dumps(
                {
                    "azure_audio_url": voice_over.azure_url_audio,
                    "youtube_url": video_link,
                }
            )
            response = requests.post(
                bg_music_url,
                data=json_data,
            )
            logging.info("Response Received")
            azure_url_audio = response.json()["output"]
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
                os.remove(
                    file_path.split("/")[-1].replace(".flac", "") + "." + export_type
                )
            except:
                logging.info("Error in removing files")
        send_audio_mail_to_user(task, azure_url_audio, user)
    else:
        logging.info("Error in exporting %s", str(task_id))


@shared_task()
def bulk_export_voiceover_async(task_ids, user_id):
    downloaded_files = []
    user = User.objects.get(pk=user_id)
    for task_id in task_ids:
        task = Task.objects.get(pk=task_id)
        voice_over = VoiceOver.objects.filter(
            task=task, status="VOICEOVER_EDIT_COMPLETE"
        ).first()

        if voice_over is not None:
            download_from_azure_blob(str(voice_over.azure_url_audio))
            logging.info(
                "Downloaded audio from Azure Blob %s", voice_over.azure_url_audio
            )
            file_path = voice_over.azure_url_audio.split("/")[-1]
            downloaded_files.append(file_path)
        else:
            logging.info("Error in exporting %s", str(task_id))

    time_now = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_file_name = f"Chitralekha_VO_Tasks_{time_now}.zip"
    with zipfile.ZipFile(zip_file_name, "w") as zf:
        for file_name in downloaded_files:
            zf.write(file_name)
    zip_file_size = os.path.getsize(zip_file_name)
    if zip_file_size > (1024**3):
        logging.info("Error: Zip file size exceeds 1 GB. Skipping upload to Azure.")
        try:
            os.remove(zip_file_name)
            for f in downloaded_files:
                os.remove(f)
        except:
            logging.info("Error in removing files")
        return
    azure_zip_url = upload_zip_to_azure(zip_file_name)
    logging.info("Uploading audio_zip to Azure Blob %s", azure_zip_url)
    try:
        os.remove(zip_file_name)
        for f in downloaded_files:
            os.remove(f)
    except:
        logging.info("Error in removing files")

    send_audio_zip_mail_to_user(task, azure_zip_url, user)
