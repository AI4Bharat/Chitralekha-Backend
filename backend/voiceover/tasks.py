import datetime
import io
from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail, EmailMultiAlternatives
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
    send_task_status_notification,
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
import regex
from datetime import datetime, timedelta
from django.utils import timezone
from django.utils.timezone import now

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
            start_time = datetime.strptime(segment["start_time"], "%H:%M:%S.%f")
            end_time = datetime.strptime(segment["end_time"], "%H:%M:%S.%f")
            unix_start_time = datetime.timestamp(start_time)
            unix_end_time = datetime.timestamp(end_time)

            updated_segment = {
                "start_time": segment["start_time"],
                "end_time": segment["end_time"],
                "target_text": segment["text"],
                "speaker_id": "",
                "unix_start_time": unix_start_time,
                "unix_end_time": unix_end_time,
                "text": segment["transcription_text"],
                "image_url": segment.get("image_url") or None,
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
    
    # Update task completion information
    if not task.completed:
        task.completed = {}
    
    task.completed.update({
        'completed_by': task.user.id,
        "timestamp": now().isoformat(),
        'audio_url': azure_url_audio
    })
    
    # Update task status
    task.status = "COMPLETE"
    voice_over_obj.save()
    task.save()
    
    # Send email notification about task completion
    try:
        # Send status change notification
        send_task_status_notification(task, voice_over_obj, "COMPLETE")
        
        logging.info("Completion emails sent to user %s for task %s", task.user.email, task.id)
    except Exception as e:
        logging.error("Error sending completion emails: %s", str(e))


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


@shared_task
def check_stalled_post_process_tasks():
    """
    Check for TRANSLATION_VOICEOVER_EDIT tasks that have been in POST_PROCESS status 
    for more than 24 hours and send notification emails to administrators.
    """
    # Find translation-voiceover tasks that have been in POST_PROCESS for more than 24 hours
    time_threshold = timezone.now() - timedelta(hours=24)
    stalled_tasks = Task.objects.filter(
        status="POST_PROCESS", 
        task_type="TRANSLATION_VOICEOVER_EDIT",
        updated_at__lt=time_threshold
    )
    
    if not stalled_tasks.exists():
        logging.info("No stalled translation-voiceover tasks found in POST_PROCESS status")
        return
    
    # Prepare email content
    task_count = stalled_tasks.count()
    subject = f"ALERT: {task_count} translation-voiceover tasks stalled in POST_PROCESS status for >24 hours"
    
    # Create HTML table of stalled tasks
    html_table = "<table border='1' style='border-collapse: collapse; width: 100%;'>"
    html_table += "<tr><th>Task ID</th><th>Video</th><th>Project</th><th>User</th><th>Time in Status (days)</th></tr>"
    
    plain_text = f"ALERT: {task_count} translation-voiceover tasks have been stalled in POST_PROCESS status for more than 24 hours.\n\n"
    plain_text += "Task Details:\n"
    
    for task in stalled_tasks:
        time_in_status = timezone.now() - task.updated_at
        days = round(time_in_status.total_seconds() / (3600 * 24), 1)  # Convert to days with one decimal place
        
        html_table += f"<tr><td>{task.id}</td><td>{task.video.name}</td>"
        html_table += f"<td>{task.video.project_id.title}</td><td>{task.user.email}</td>"
        html_table += f"<td>{days} days</td></tr>"
        
        plain_text += f"- Task #{task.id}: Video '{task.video.name}' in project '{task.video.project_id.title}' "
        plain_text += f"by user {task.user.email}, stalled for {days} days\n"
    
    html_table += "</table>"
    
    html_message = f"""
    <html>
    <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333333;">
        <h2>Stalled Translation-Voiceover Tasks Notification</h2>
        <p>The following {task_count} translation-voiceover tasks have been in POST_PROCESS status for more than 24 hours:</p>
        
        {html_table}
        
        <p style="margin-top: 20px;">
            Please check these tasks in the Chitralekha dashboard and take appropriate action.
        </p>
    </body>
    </html>
    """
    
    # Send email to administrators
    recipients = [
        'aparna@ai4bharat.org', 
        'kartikvirendrarajput@gmail.com', 
        'aswathyvinod@ai4bharat.org'
    ]
    
    msg = EmailMultiAlternatives(
        subject,
        plain_text,
        settings.DEFAULT_FROM_EMAIL,
        recipients
    )
    msg.attach_alternative(html_message, "text/html")
    
    try:
        msg.send()
        logging.info(f"Stalled translation-voiceover tasks notification email sent to administrators. Found {task_count} stalled tasks.")
    except Exception as e:
        logging.error(f"Error sending stalled tasks notification email: {str(e)}")
