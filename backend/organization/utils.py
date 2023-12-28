from translation.metadata import TRANSLATION_LANGUAGE_CHOICES
from django.db.models import (
    Q,
    Count,
    Avg,
    F,
    FloatField,
    BigIntegerField,
    Sum,
    Value,
    Case,
    When,
    IntegerField,
)
from django.db.models.functions import Cast, Concat
from datetime import timedelta, datetime
from django.core.mail import send_mail, EmailMessage
import os
from organization.models import Organization
from project.models import Project
from project.views import ProjectViewSet
from django.http import HttpRequest
import pandas as pd
from project.utils import send_mail_with_report
from transcript.models import Transcript
from translation.models import Translation
from voiceover.models import VoiceOver
from video.models import Video
from task.models import Task


def get_project_report_users(project_id, user):
    data = ProjectViewSet(detail=True)
    new_request = HttpRequest()
    new_request.user = user
    ret = data.get_report_users(new_request, project_id)
    return ret.data


def task_search_filter(videos, search_dict, filter_dict):
    if search_dict is not None:
        if "video_name" in search_dict:
            videos = videos.filter(Q(name__icontains=search_dict["video_name"]))

    if "src_language" in filter_dict and len(filter_dict["src_language"]):
        src_lang_list = []
        for lang in filter_dict["src_language"]:
            lang_shortcode = get_language_label(lang)
            src_lang_list.append(lang_shortcode)
        if len(src_lang_list):
            videos = videos.filter(language__in=src_lang_list)

    return videos


def task_filter_query(all_tasks, filter_dict):
    if "task_type" in filter_dict and len(filter_dict["task_type"]):
        all_tasks = all_tasks.filter(task_type__in=filter_dict["task_type"])
    if "target_language" in filter_dict and len(filter_dict["target_language"]):
        target_lang_list = []
        for lang in filter_dict["target_language"]:
            lang_shortcode = get_language_label(lang)
            target_lang_list.append(lang_shortcode)
        if len(target_lang_list):
            all_tasks = all_tasks.filter(target_language__in=target_lang_list)
    if "status" in filter_dict and len(filter_dict["status"]):
        all_tasks = all_tasks.filter(status__in=filter_dict["status"])

    return all_tasks


def task_search_by_assignee(all_tasks, search_dict):
    if "assignee" in search_dict and len(search_dict["assignee"]):
        queryset = all_tasks.annotate(
            search_name=Concat("user__first_name", Value(" "), "user__last_name")
        )
        all_tasks = queryset.filter(search_name__icontains=search_dict["assignee"])

    return all_tasks


def task_search_by_task_id(all_tasks, search_dict):
    if "task_id" in search_dict and search_dict["task_id"] != None:
        all_tasks = all_tasks.filter(Q(pk=search_dict["task_id"]))
    return all_tasks


def task_search_by_description(all_tasks, search_dict):
    if "description" in search_dict and len(search_dict["description"]):
        all_tasks = all_tasks.filter(
            Q(description__icontains=search_dict["description"])
            | Q(description__icontains=search_dict["description"])
        )
    return all_tasks


def get_language_label(target_language):
    for language in TRANSLATION_LANGUAGE_CHOICES:
        if target_language == language[1]:
            return language[0]
    return "-"

def search_active_task(all_tasks, search_dict):
    if "active" in search_dict:
        all_tasks = all_tasks.filter(is_active=True)
    if "non_active" in search_dict:
        all_tasks = all_tasks.filter(is_active=False)
    return all_tasks


def get_org_report_users_email(org_id, user):
    org = Organization.objects.get(pk=org_id)
    projects_in_org = Project.objects.filter(organization_id=org).all()
    user_data = []
    if len(projects_in_org) > 0:
        for project in projects_in_org:
            project_report = get_project_report_users(project.id, user)
            for report in project_report:
                report["project"] = {"value": project.title, "label": "Project"}
                user_data.append(report)
    columns = [field["label"] for field in user_data[0].values()]

    data = [[field["value"] for field in row.values()] for row in user_data]
    current_time = datetime.now()

    df = pd.DataFrame(data, columns=columns)
    csv_file_path = "organization_user_reports_{}_{}.csv".format(org.id, current_time)
    df.to_csv(csv_file_path, index=False)

    subject = f"User Reports for Organization - {org.title}"
    body = "Please find the attached CSV file."
    send_mail_with_report(subject, body, user, csv_file_path)


def get_org_report_languages_email(org_id, user):
    org = Organization.objects.get(pk=org_id)
    projects_in_org = Project.objects.filter(organization_id=org).all()
    user_data = []
    if len(projects_in_org) > 0:
        for project in projects_in_org:
            project_report = get_project_report_users(project.id, user)
            for report in project_report:
                report["project"] = {"value": project.title, "label": "Project"}
                user_data.append(report)
    columns = [field["label"] for field in user_data[0].values()]

    data = [[field["value"] for field in row.values()] for row in user_data]
    current_time = datetime.now()

    df = pd.DataFrame(data, columns=columns)
    csv_file_path = "organization_user_reports_{}_{}.csv".format(org.id, current_time)
    df.to_csv(csv_file_path, index=False)

    subject = f"User Reports for Project - {org.title}"
    body = "Please find the attached CSV file."
    send_mail_with_report(subject, body, user, csv_file_path)


def get_org_report_tasks(pk, user):
    org_videos = Video.objects.filter(project_id__organization_id=pk)
    task_orgs = Task.objects.filter(video__in=org_videos)
    tasks_list = []
    for task in task_orgs:
        if task.description is not None:
            description = task.description
        elif task.video.description is not None:
            description = task.video.description
        else:
            description = None

        if "COMPLETE" in task.status:
            datetime_str = task.updated_at
            updated_at_str = task.updated_at.strftime("%m-%d-%Y %H:%M:%S.%f")
            updated_at_datetime_object = datetime.strptime(
                updated_at_str, "%m-%d-%Y %H:%M:%S.%f"
            )
            compare_with = "05-04-2023 17:00:00.000"
            compare_with_datetime_object = datetime.strptime(
                compare_with, "%m-%d-%Y %H:%M:%S.%f"
            )

            if updated_at_datetime_object < compare_with_datetime_object:
                time_spent = float(
                    "{:.2f}".format((task.updated_at - task.created_at).total_seconds())
                )
            else:
                time_spent = task.time_spent
            completion_time = self.format_completion_time(time_spent)
        else:
            completion_time = None

        word_count = 0
        if "Translation" in task.get_task_type_label:
            try:
                translation_obj = Translation.objects.filter(task=task).first()
                word_count = translation_obj.payload["word_count"]
            except:
                pass
        elif "Transcription" in task.get_task_type_label:
            try:
                transcript_obj = Transcript.objects.filter(task=task).first()
                word_count = transcript_obj.payload["word_count"]
            except:
                pass
        elif "VoiceOver" in task.get_task_type_label:
            word_count = "-"

        tasks_list.append(
            {
                "project_name": {
                    "value": task.video.project_id.title,
                    "label": "Project Name",
                    "viewColumns": False,
                },
                "video_name": {
                    "value": task.video.name,
                    "label": "Video Name",
                    "viewColumns": False,
                },
                "video_url": {
                    "value": task.video.url,
                    "label": "Video URL",
                    "display": "exclude",
                },
                "duration": {
                    "value": str(task.video.duration),
                    "label": "Duration",
                },
                "task_type": {
                    "value": task.get_task_type_label,
                    "label": "Task Type",
                    "viewColumns": False,
                },
                "task_description": {
                    "value": description,
                    "label": "Task Description",
                    "display": "exclude",
                },
                "source_language": {
                    "value": task.get_src_language_label,
                    "label": "Source Langauge",
                    "viewColumns": False,
                },
                "target_language": {
                    "value": task.get_target_language_label,
                    "label": "Target Langauge",
                    "viewColumns": False,
                },
                "assignee": {
                    "value": task.user.email,
                    "label": "Assignee",
                },
                "status": {"value": task.get_task_status_label, "label": "Status"},
                "completion_time": {
                    "value": completion_time,
                    "label": "Completion Time",
                    "display": "exclude",
                },
                "word_count": {
                    "value": word_count,
                    "label": "Word Count",
                },
            }
        )
    return tasks_list


def get_org_report_tasks_email(org_id, user):
    tasks_list = get_org_report_tasks(org_id, user)
    columns = [field["label"] for field in tasks_list[0].values()]

    data = [[field["value"] for field in row.values()] for row in tasks_list]
    current_time = datetime.now()

    df = pd.DataFrame(data, columns=columns)
    csv_file_path = "organization_tasks_reports_{}_{}.csv".format(org_id, current_time)
    df.to_csv(csv_file_path, index=False)

    subject = f"Tasks Reports for Organization - {org_id}"
    body = "Please find the attached CSV file."
    send_mail_with_report(subject, body, user, csv_file_path)


def get_org_report_projects(pk, user):
    org_projects = (
        Project.objects.filter(organization_id=pk).values("title", "id").order_by("id")
    )

    project_stats = org_projects.annotate(num_videos=Count("video"))

    video_duration_transcripts = org_projects.annotate(
        total_transcriptions=Sum(
            "video__duration",
            filter=Q(video__transcripts__status="TRANSCRIPTION_EDIT_COMPLETE"),
        )
    )

    video_duration_translations = org_projects.annotate(
        total_translations=Sum(
            "video__duration",
            filter=Q(video__translation_video__status="TRANSLATION_EDIT_COMPLETE"),
        )
    )

    word_count_transcripts = org_projects.annotate(
        word_count=Sum(
            Cast(F("video__transcripts__payload__word_count"), FloatField()),
            filter=Q(video__transcripts__status__in=["TRANSCRIPTION_EDIT_COMPLETE"]),
        )
    )

    word_count_translations = org_projects.annotate(
        word_count=Sum(
            Cast(F("video__translation_video__payload__word_count"), FloatField()),
            filter=Q(
                video__translation_video__status__in=["TRANSLATION_EDIT_COMPLETE"]
            ),
        )
    )

    project_data = []
    idx = 0
    for elem in project_stats:
        manager_names = Project.objects.get(pk=elem["id"]).managers.all()
        manager_list = []
        for manager_name in manager_names:
            manager_list.append(manager_name.first_name + " " + manager_name.last_name)
        transcript_duration = (
            None
            if video_duration_transcripts[idx]["total_transcriptions"] is None
            else round(
                video_duration_transcripts[idx]["total_transcriptions"].total_seconds()
                / 3600,
                3,
            )
        )
        transcript_word_count = (
            0
            if word_count_transcripts[idx]["word_count"] is None
            else word_count_transcripts[idx]["word_count"]
        )
        translation_duration = (
            None
            if video_duration_translations[idx]["total_translations"] is None
            else round(
                video_duration_translations[idx]["total_translations"].total_seconds()
                / 3600,
                3,
            )
        )
        translation_word_count = (
            0
            if word_count_translations[idx]["word_count"] is None
            else word_count_translations[idx]["word_count"]
        )
        project_dict = {
            "title": {"value": elem["title"], "label": "Title", "viewColumns": False},
            "managers__username": {
                "value": manager_list,
                "label": "Managers",
                "viewColumns": False,
            },
            "num_videos": {"value": elem["num_videos"], "label": "Video count"},
            "total_transcriptions": {
                "value": transcript_duration,
                "label": "Duration (Hours)",
            },
            "total_translations": {
                "value": translation_duration,
                "label": "Duration (Hours)",
            },
            "total_word_count": {
                "value": int(transcript_word_count + translation_word_count),
                "label": "Total Word Count",
            },
        }
        project_data.append(project_dict)
        idx += 1
    return project_data


def get_org_report_projects_email(org_id, user):
    projects_list = get_org_report_projects(org_id, user)
    columns = [field["label"] for field in projects_list[0].values()]

    data = [[field["value"] for field in row.values()] for row in projects_list]
    current_time = datetime.now()

    df = pd.DataFrame(data, columns=columns)
    csv_file_path = "organization_projects_reports_{}_{}.csv".format(
        org_id, current_time
    )
    df.to_csv(csv_file_path, index=False)

    subject = f"Projects Reports for Organization - {org_id}"
    body = "Please find the attached CSV file."
    send_mail_with_report(subject, body, user, csv_file_path)
