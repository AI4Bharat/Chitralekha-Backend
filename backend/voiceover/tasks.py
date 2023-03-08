from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail
from celery.schedules import crontab
from datetime import datetime
from rest_framework.response import Response
from rest_framework import status
from pretty_html_table import build_table


@shared_task(name="integrate_audio_with_video_asynchronously")
def integrate_audio_with_video_asynchronously(task_id, source_type):
    task = Tasks.objects.get(task_id)
    payloads = generate_transcript_payload(task, source_type)
