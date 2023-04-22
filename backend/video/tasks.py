from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail
from celery.schedules import crontab
from datetime import datetime
from rest_framework.response import Response
from rest_framework import status
from video.models import Video
import os
import logging
from video.utils import create_video


@shared_task()
def create_videos_async(user_id, valid_rows, existing_videos, project_id):
    logging.info("Creating videos Asynchronously")
    for row in valid_rows:
        create_video(
            user_id,
            row["url"],
            project_id,
            row["description"],
            row["gender"],
            row["task_type"],
            row["target_language"],
            row["assignee"],
            row["lang"],
        )
