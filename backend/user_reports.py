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
from django.core.mail import send_mail, EmailMultiAlternatives
from django.conf import settings
from pretty_html_table import build_table
import numpy as np
import datetime
from datetime import timedelta, datetime
from django.utils import timezone
from django.utils.timezone import localdate, localtime, now
from users.models import User
from video.models import Video
import logging
from organization.models import Organization
from config import app_name
from utils.email_template import send_email_template_with_attachment


def get_completed_tasks():
    logging.info("Calculate Reports...")
    current_time = localtime(now())
    logging.info("current_time %s", str(current_time))
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
                logging.info("Task ID %s", str(task.id))
                tasks_managed.append(
                    {
                        "Project Name": task.video.project_id.title,
                        "Task ID": task.id,
                        "Task Type": task.get_task_type_label,
                        "Video Name": task.video.name,
                        "Video Url": task.video.url,
                        "Task Assignee": task.user,
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
                message = (
                    "Hope you are doing great  "
                    + str(manager.first_name + " " + manager.last_name)
                    + ",\n Following tasks are completed now."
                )

                email_to_send = (
                    "<p>"
                    + message
                    + "</p><br><h1><b>Tasks Reports</b></h1>"
                    + html_table_df_tasks
                )
                logging.info("Sending Mail to %s", manager.email)

                compiled_msg = send_email_template_with_attachment(
                    subject=f"{app_name} - Completed Tasks Report",
                    username=[manager.email],
                    message=email_to_send,
                )
                msg = EmailMultiAlternatives(
                    f"{app_name} - Completed Tasks Report",
                    compiled_msg,
                    settings.DEFAULT_FROM_EMAIL,
                    [manager.email],
                )
                email_content = compiled_msg + html_table_df_tasks
                msg.attach_alternative(email_content, "text/html")
                msg.send()
                # send_mail(
                #     f"{app_name} - Completed Tasks Report",
                #     message,
                #     settings.DEFAULT_FROM_EMAIL,
                #     [manager.email],
                #     html_message=email_to_send,
                # )
            else:
                html_table_df_tasks = ""

def get_active_tasks(ids_array):
    users = User.objects.filter(id__in=ids_array)
    for member in list(users):
        tasks_managed = []
        tasks = (
            Task.objects
            .filter(status__in=["INPROGRESS", "SELECTED_SOURCE"])
            .filter(is_active=True)
            .filter(user=member)
        )
        for task in tasks:
            if task.get_task_type_label.count("VoiceOver"):
                type = "voiceover"
            elif task.get_task_type_label.count("Translation"):
                type = "translate"
            else:
                type = "transcript"
            task_link = f"https://chitralekha.ai4bharat.org/#/task/{task.id}/{type}"
            tasks_managed.append(
                {
                    "Project Name": task.video.project_id.title,
                    "Project Id": task.video.project_id.id,
                    "Task ID": task.id,
                    "Task Type": task.get_task_type_label,
                    "Task Link": f'<a href="{task_link}" target="_blank">Open Task</a>'
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
                escape=False,
            )
            message = (
                "Hope you are doing great  "
                + str(member.first_name + " " + member.last_name)
                + ",\n Following tasks are active now."
            )

            email_to_send = (
                "<p>"
                + message
                + "</p><br><h1><b>Active Tasks Reports</b></h1>"
                + html_table_df_tasks
            )
            logging.info("Sending Mail to %s", member.email)

            compiled_msg = send_email_template_with_attachment(
                subject=f"{app_name} - Active Tasks Report",
                username=[member.email],
                message=email_to_send,
            )
            msg = EmailMultiAlternatives(
                f"{app_name} - Active Tasks Report",
                compiled_msg,
                settings.DEFAULT_FROM_EMAIL,
                [member.email],
            )
            email_content = compiled_msg
            msg.attach_alternative(email_content, "text/html")
            msg.send()
        else:
            html_table_df_tasks = ""


def get_new_tasks():
    logging.info("Calculate Reports...")
    current_time = localtime(now())
    logging.info("current_time %s", str(current_time))
    three_hours_earlier = current_time - timedelta(hours=24)
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
                .filter(status__in=["SELECTED_SOURCE", "NEW"])
                .filter(is_active=True)
                .filter(updated_at__range=(three_hours_earlier, current_time))
            )
            for task in tasks_in_project:
                logging.info("Task ID %s", str(task.id))
                tasks_managed.append(
                    {
                        "Project Name": task.video.project_id.title,
                        "Task ID": task.id,
                        "Task Type": task.get_task_type_label,
                        "Video Name": task.video.name,
                        "Video Url": task.video.url,
                        "Task Assignee": task.user,
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
                message = (
                    "Hope you were doing great  "
                    + str(manager.first_name + " " + manager.last_name)
                    + ",\n Following tasks are active now."
                )

                email_to_send = (
                    "<p>"
                    + message
                    + "</p><br><h1><b>Tasks Reports</b></h1>"
                    + html_table_df_tasks
                )
                logging.info("Sending Mail to %s", manager.email)

                compiled_msg = send_email_template_with_attachment(
                    subject=f"{app_name} - Tasks Assignment Status Report",
                    username=[manager.email],
                    message=email_to_send,
                )
                msg = EmailMultiAlternatives(
                    f"{app_name} - Tasks Assignment Status Report",
                    compiled_msg,
                    settings.DEFAULT_FROM_EMAIL,
                    [manager.email],
                )
                email_content = compiled_msg + html_table_df_tasks
                msg.attach_alternative(email_content, "text/html")
                msg.send()

                # send_mail(
                #     f"{app_name} - Tasks Assignment Status Report",
                #     message,
                #     settings.DEFAULT_FROM_EMAIL,
                #     [manager.email],
                #     html_message=email_to_send,
                # )
            else:
                html_table_df_tasks = ""


def get_eta_reminders():
    users = User.objects.filter(enable_mail=True).filter(has_accepted_invite=True).all()
    now = timezone.now()
    eta_today = now + timezone.timedelta(hours=1)

    # Get all objects created in the past 24 hours
    for user in users:
        tasks_assigned = (
            Task.objects.filter(user=user)
            .filter(eta__date=eta_today)
            .filter(is_active=True)
            .all()
        )
        task_assigned_info = []
        for task in tasks_assigned:
            task_assigned_info.append(
                {
                    "Task ID": task.id,
                    "Task Type": task.get_task_type_label,
                    "Video Name": task.video.name,
                    "Video Url": task.video.url,
                }
            )
        if len(task_assigned_info) > 0:
            df = pd.DataFrame.from_records(task_assigned_info)
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
                "Hope you are doing great  "
                + str(user.first_name + " " + user.last_name)
                + ",\n Follwing Tasks are due for today."
            )

            email_to_send = (
                "<p>"
                + message
                + "</p><br><h1><b>Due Tasks For Today</b></h1>"
                + html_table_df_tasks
            )
            logging.info("Sending Mail to %s", user.email)

            compiled_msg = send_email_template_with_attachment(
                subject=f"{app_name} - Tasks Assignment Status Report",
                username=[user.email],
                message=email_to_send,
            )
            msg = EmailMultiAlternatives(
                f"{app_name} - Tasks Assignment Status Report",
                compiled_msg,
                settings.DEFAULT_FROM_EMAIL,
                [user.email],
            )
            msg.attach_alternative(compiled_msg, "text/html")
            msg.send()
            # send_mail(
            #     f"{app_name} - Due Tasks",
            #     message,
            #     settings.DEFAULT_FROM_EMAIL,
            #     [user.email],
            #     html_message=email_to_send,
            # )
        else:
            html_table_df_tasks = ""


def get_new_users():
    organization_owners = list(
        set(
            chain.from_iterable(
                organization.organization_owners.all()
                for organization in Organization.objects.all()
            )
        )
    )

    now = timezone.now()
    past_24_hours = now - timezone.timedelta(hours=24)
    users = User.objects.filter(date_joined__gte=past_24_hours)

    # Get all objects created in the past 24 hours
    for org_owner in organization_owners:
        users_in_org = users.filter(organization=org_owner.organization)
        new_users = []
        for user in users_in_org:
            new_users.append(
                {
                    "Email": user.email,
                    "Role": user.get_role_label,
                    "Name": user.first_name + " " + user.last_name,
                    "Languages": ", ".join(user.languages),
                }
            )
        if len(new_users) > 0:
            df = pd.DataFrame.from_records(new_users)
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
                + str(org_owner.first_name + " " + org_owner.last_name)
                + ",\n Following users have signed up."
            )
            email_to_send = (
                "<p>"
                + message
                + "</p><br><h1><b>New Users</b></h1>"
                + html_table_df_tasks
            )
            logging.info("Sending Mail to %s", org_owner.email)
            compiled_msg = send_email_template_with_attachment(
                subject=f"{app_name} - New Users",
                username=[user.email],
                message=email_to_send,
            )
            msg = EmailMultiAlternatives(
                f"{app_name} - New Users",
                compiled_msg,
                settings.DEFAULT_FROM_EMAIL,
                [user.email],
            )
            msg.attach_alternative(compiled_msg, "text/html")
            # msg.attach_alternative(html_table_df_tasks, "text/html")
            msg.send()
            # send_mail(
            #     f"{app_name} - New Users",
            #     message,
            #     settings.DEFAULT_FROM_EMAIL,
            #     [org_owner.email],
            #     html_message=email_to_send,
            # )
        else:
            html_table_df_tasks = ""
