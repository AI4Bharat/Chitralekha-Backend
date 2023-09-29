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
from django.core.mail import send_mail
from users.models import User
import pandas as pd
from pretty_html_table import build_table
from django.conf import settings


def send_mail_csv_upload(user_id, email_data):
    user = User.objects.get(pk=user_id)
    df = pd.DataFrame.from_records(email_data)
    df.rename(
        columns={
            "video_name": "Video Name",
            "video_url": "Video URL",
            "task_type": "Task Type",
            "language_pair": "Language Pair",
            "status": "Status",
            "message": "Message",
        },
        inplace=True,
    )
    blankIndex = [""] * len(df)
    df.index = blankIndex
    html_table_df_tasks = build_table(
        df,
        "orange_light",
        font_size="medium",
        text_align="left",
        width="auto",
        index=False,
    )
    message = (
        "Dear "
        + str(user.first_name + " " + user.last_name)
        + ",\n Following is the CSV upload report."
    )

    email_to_send = (
        "<p>"
        + message
        + "</p><br><h1><b>CSV Upload Reports</b></h1>"
        + html_table_df_tasks
    )
    logging.info("Sending Mail to %s", user.email)
    try:
        send_mail(
            "Chitralekha - CSV Upload Reports",
            message,
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
            html_message=email_to_send,
        )
    except:
        logging.info("Error in sending mail")


@shared_task()
def create_videos_async(user_id, valid_rows, existing_videos, project_id):
    logging.info("Creating videos Asynchronously")
    email_data = []
    for row in valid_rows:
        if "project_id" in row.keys():
            project_id = row["project_id"]
        creation = create_video(
            user_id,
            row["url"],
            project_id,
            row["task_description"],
            row["video_description"],
            row["ETA"],
            row["gender"],
            row["task_type"],
            row["target_language"],
            row["assignee"],
            row["lang"],
        )
        if "detailed_report" in creation.data.keys():
            if len(creation.data["detailed_report"]) > 0:
                email_data.append(creation.data["detailed_report"][0])
    if len(email_data) > 0:
        send_mail_csv_upload(user_id, email_data)
