import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings")
django.setup()
import requests
import time
from requests.auth import HTTPBasicAuth
import json
from users.models import User
from project.models import Project
from task.models import Task
from datetime import datetime, timedelta
from django.db.models import Q
import pandas as pd
from django.core.mail import send_mail
from django.conf import settings
from pretty_html_table import build_table
import numpy as np
import datetime
from datetime import timedelta, datetime
from django.utils import timezone
from django.utils.timezone import localdate, localtime, now
from users.models import User
from video.models import Video


def calculate_reports():
    current_time = localtime(now())
    three_hours_earlier = current_time - timedelta(hours=6)
    projects = Project.objects.all()
    project_managers = {}
    for project in list(projects):
        project_managers[project.id] = list(project.managers.all())

    for project, managers in project_managers.items():
        for manager in managers:
            if not manager.enable_mail:
                continue
            tasks_managed = []
            videos = Video.objects.filter(project_id=project)
            tasks_in_project = (
                Task.objects.filter(video__in=videos)
                .filter(status__in=["COMPLETE"])
                .filter(is_active=True)
                .filter(updated_at__range=(three_hours_earlier, current_time))
            )
            for task in tasks_in_project:
                tasks_managed.append(
                    {
                        "project_name": task.video.project_id.title,
                        "task_type": task.get_task_type_label,
                        "video_name": task.video.name,
                        "video_url": task.video.url,
                        "task_assignee": task.user,
                    }
                )
            if len(tasks_managed) > 0:
                df = pd.DataFrame.from_records(tasks_managed)
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
            else:
                html_table_df_tasks = ""

            message = (
                "Dear "
                + str(manager.first_name + " " + manager.last_name)
                + ",\n Following tasks that are assigned to you are active now "
                + " .\n Thanks for contributing on Chitralekha!"
            )

            email_to_send = (
                "<p>"
                + message
                + "</p><br><h1><b>Tasks Reports</b></h1>"
                + html_table_df_tasks
            )
            send_mail(
                "Tasks Reports",
                message,
                settings.DEFAULT_FROM_EMAIL,
                [manager.email],
                html_message=email_to_send,
            )
