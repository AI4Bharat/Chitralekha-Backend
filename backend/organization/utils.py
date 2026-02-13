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
import os
from organization.models import Organization
from project.models import Project
from users.models import User
from project.views import ProjectViewSet
from project.utils import *
from django.http import HttpRequest
import pandas as pd
from transcript.models import Transcript
from translation.models import Translation
from voiceover.models import VoiceOver
from video.models import Video
from task.models import Task
from utils.storage_factory import get_storage_provider
from config import storage_account_key, connection_string, reports_container_name
from django.conf import settings
import logging
from collections import defaultdict
from django.core.mail import EmailMultiAlternatives
from utils.email_template import send_email_template_with_attachment


def send_mail_with_report(subject, body, user, csv_file_paths):
    storage = get_storage_provider(reports_container=True)
    report_urls = []

    for file_path in csv_file_paths:
        local_file = file_path
        remote_file = file_path

        try:
            url = storage.upload(local_file, remote_file)
            logging.info("Report uploaded successfully!")
            logging.info(url)
            report_urls.append(url)
        except Exception as e:
            logging.info("This report can't be uploaded")

    if len(report_urls) == 1:
        try:
            reports_message = """<p>The requested report has been successfully generated. <br><br><a href={url} target="_blank">Click Here</a> to access the reports.</p>""".format(
                url=report_urls[0]
            )
            compiled_msg_code = send_email_template_with_attachment(
                subject=subject, username=[user.email], message=reports_message
            )

            msg = EmailMultiAlternatives(
                subject,
                compiled_msg_code,
                settings.DEFAULT_FROM_EMAIL,
                [user.email],
            )
            msg.attach_alternative(compiled_msg_code, "text/html")
            msg.send()
            # send_mail(
            #     subject,
            #     "",
            #     settings.DEFAULT_FROM_EMAIL,
            #     [user.email],
            #     html_message=reports_message,
            # )
        except:
            logging.info("Email Can't be sent.")
    else:
        try:
            reports_msg = """<p>The requested report has been successfully generated. <br><br><a href={url_1} target="_blank">Click Here</a> to access the Transcription reports.<br><br><a href={url_2} target="_blank">Click Here</a> to access the Translation reports.<br><br><a href={url_3} target="_blank">Click Here</a> to access the VoiceOver reports.</p>""".format(
                url_1=report_urls[0], url_2=report_urls[1], url_3=report_urls[2]
            )
            compiled_msg_code = send_email_template_with_attachment(
                subject=subject, username=[user.email], message=reports_message
            )

            msg = EmailMultiAlternatives(
                f"Chitralekha User Reports",
                compiled_msg_code,
                settings.DEFAULT_FROM_EMAIL,
                [user.email],
            )
            msg.attach_alternative(compiled_msg_code, reports_msg, "text/html")
            msg.send()
            # send_mail(
            #     subject,
            #     "",
            #     settings.DEFAULT_FROM_EMAIL,
            #     [user.email],
            #     html_message=reports_msg,
            # )
        except:
            logging.info("Email Can't be sent.")

    for file_path in csv_file_paths:
        os.remove(file_path)


def get_project_report_users(project_id, user, limit):
    data = ProjectViewSet(detail=True)
    new_request = HttpRequest()
    new_request.user = user
    new_request.query_params = {"offset": 1, "limit": limit}
    params = {"offset": 1, "limit": limit}
    ret = data.get_report_users(new_request, project_id)
    return ret.data["reports"]


def get_project_report_languages(project_id, user):
    ret = get_reports_for_languages(project_id)
    return ret


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
            limit = len(
                User.objects.filter(projects__pk=project.id, has_accepted_invite=True)
            )
            project_report = get_project_report_users(project.id, user, limit)
            for report in project_report:
                report["project"] = {"value": project.title, "label": "Project"}
                user_data.append(report)
    columns = [field["label"] for field in user_data[0].values()]

    data = [[field["value"] for field in row.values()] for row in user_data]
    current_time = datetime.now()

    df = pd.DataFrame(data, columns=columns)
    csv_file_path = "organization_user_reports_{}_{}.csv".format(
        org.title, current_time
    )
    df.to_csv(csv_file_path, index=False)

    formatted_date = current_time.strftime("%d %b")
    subject = f"User Reports for Organization - {org.title} - {formatted_date}"
    body = "Please find the attached CSV file."
    send_mail_with_report(subject, body, user, [csv_file_path])


def get_org_report_languages(org_id, user):
    projects_in_org = Project.objects.filter(organization_id__id=org_id).all()
    all_project_report = []
    if len(projects_in_org) > 0:
        for project in projects_in_org:
            project_report = get_project_report_languages(project.id, user)
            for keys, values in project_report.items():
                for report in values:
                    report["project"] = {
                        "value": project.title,
                        "label": "Project",
                        "viewColumns": False,
                    }
            all_project_report.append(project_report)

    aggregated_project_report = {
        "transcript_stats": [],
        "translation_stats": [],
        "voiceover_stats": [],
        "translation_voiceover_stats": [],
    }
    for project_report in all_project_report:
        if type(project_report) == dict:
            if (
                "transcript_stats" in project_report.keys()
                and len(project_report["transcript_stats"]) > 0
            ):
                for i in range(len(project_report["transcript_stats"])):
                    new_stats = dict(
                        reversed(list(project_report["transcript_stats"][i].items()))
                    )
                    project_report["transcript_stats"][i] = new_stats
                dict(reversed(list(report.items())))
                aggregated_project_report["transcript_stats"].extend(
                    project_report["transcript_stats"]
                )
            if (
                "translation_stats" in project_report.keys()
                and len(project_report["translation_stats"]) > 0
            ):
                for i in range(len(project_report["translation_stats"])):
                    new_stats = dict(
                        reversed(list(project_report["translation_stats"][i].items()))
                    )
                    project_report["translation_stats"][i] = new_stats
                aggregated_project_report["translation_stats"].extend(
                    project_report["translation_stats"]
                )
            if (
                "voiceover_stats" in project_report.keys()
                and len(project_report["voiceover_stats"]) > 0
            ):
                for i in range(len(project_report["voiceover_stats"])):
                    new_stats = dict(
                        reversed(list(project_report["voiceover_stats"][i].items()))
                    )
                    project_report["voiceover_stats"][i] = new_stats
                aggregated_project_report["voiceover_stats"].extend(
                    project_report["voiceover_stats"]
                )
            translation_stats = project_report.get("translation_stats", [])
            voiceover_stats = project_report.get("voiceover_stats", [])
            for translation in translation_stats:
                for voiceover in voiceover_stats:
                    if (
                        translation["src_language"]["value"] == voiceover["src_language"]["value"]
                        and translation["tgt_language"]["value"] == voiceover["tgt_language"]["value"]
                    ):
                        merged_stat = {
                            "project": translation["project"],
                            "src_language": translation["src_language"],
                            "tgt_language": translation["tgt_language"],
                            "translation_duration": translation["translation_duration"],  
                            "translation_tasks_count": translation["transcripts_translated"],  
                            "word_count": translation["word_count"],  # Taken from translation
                            "voiceover_duration": voiceover["voiceover_duration"],
                            "voiceover_tasks_count": voiceover["voiceovers_completed"],
                        }
                        aggregated_project_report["translation_voiceover_stats"].append(merged_stat)
    
    return aggregated_project_report


def get_org_report_languages_email(org_id, user):
    org = Organization.objects.get(pk=org_id)
    data = get_org_report_languages(org_id, user)
    csv_file_paths = []

    def write_csv_pandas(file_name, data_list):
        df = pd.DataFrame(data_list)
        df.to_csv(file_name, index=False)
        csv_file_paths.append(file_name)

    for section in ["transcript_stats", "translation_stats", "voiceover_stats"]:
        if section in data:
            for entry in data[section]:
                keys_to_remove = [
                    key
                    for key in entry.keys()
                    if isinstance(entry[key], dict) and "label" in entry[key]
                ]
                for key in keys_to_remove:
                    label = entry[key]["label"]
                    entry[label] = entry[key]["value"]
                    del entry[key]
    current_time = datetime.now()
    write_csv_pandas(
        "transcript_stats_{}_{}.csv".format(org_id, current_time),
        data["transcript_stats"],
    )
    write_csv_pandas(
        "translation_stats_{}_{}.csv".format(org_id, current_time),
        data["translation_stats"],
    )
    write_csv_pandas(
        "voiceover_stats_{}_{}.csv".format(org_id, current_time),
        data["voiceover_stats"],
    )

    formatted_date = current_time.strftime("%d %b")
    subject = f"Languages Reports for Organization - {org.title} - {formatted_date}"
    body = "Please find the attached CSV file."
    send_mail_with_report(subject, body, user, csv_file_paths)


def format_completion_time(completion_time):
    if completion_time < 60 * 60:
        full_time = (
            str(int(completion_time // 60))
            + "m "
            + str(int(completion_time % 60))
            + "s"
        )
    elif completion_time >= 60 * 60 and completion_time < 24 * 60 * 60:
        full_time = (
            str(int(completion_time // (60 * 60)))
            + "h "
            + str(int((completion_time % (60 * 60)) // 60))
            + "m"
        )
    elif completion_time >= 24 * 60 * 60 and completion_time < 30 * 24 * 60 * 60:
        full_time = (
            str(int(completion_time // (24 * 60 * 60)))
            + "d "
            + str(int((completion_time % (24 * 60 * 60)) // (60 * 60)))
            + "h"
        )
    elif (
        completion_time >= 30 * 24 * 60 * 60
        and completion_time < 12 * 30 * 24 * 60 * 60
    ):
        full_time = (
            str(int(completion_time // (30 * 24 * 60 * 60)))
            + "m "
            + str(int((completion_time % (30 * 24 * 60 * 60)) // (24 * 60 * 60)))
            + "d"
        )
    else:
        full_time = (
            str(int(completion_time // (12 * 30 * 24 * 60 * 60)))
            + "y "
            + str(
                int((completion_time % (12 * 30 * 24 * 60 * 60)) // (30 * 24 * 60 * 60))
            )
            + "m"
        )
    return full_time


def get_org_report_tasks(
    pk,
    user,
    limit,
    offset,
    taskStartDate="2020-01-01",
    taskEndDate=datetime.now().date(),
    filter_dict={},
):
    if limit != "All" and limit != "undefined":
        start_offset = (int(offset) - 1) * int(limit)
        end_offset = start_offset + int(limit)

    if "src_language" in filter_dict and len(filter_dict["src_language"]):
        src_lang_list = []
        for lang in filter_dict["src_language"]:
            lang_shortcode = get_language_label(lang)
            src_lang_list.append(lang_shortcode)
        if len(src_lang_list):
            org_videos = Video.objects.filter(
                project_id__organization_id=pk, language__in=src_lang_list
            )
    else:
        org_videos = Video.objects.filter(project_id__organization_id=pk)
    task_orgs = Task.objects.filter(
        video__in=org_videos, created_at__date__range=(taskStartDate, taskEndDate)
    ).order_by("-created_at")
    total_count = len(task_orgs)
    if "task_type" in filter_dict and len(filter_dict["task_type"]):
        task_orgs = task_orgs.filter(task_type__in=filter_dict["task_type"])
    if "target_language" in filter_dict and len(filter_dict["target_language"]):
        target_lang_list = []
        for lang in filter_dict["target_language"]:
            lang_shortcode = get_language_label(lang)
            target_lang_list.append(lang_shortcode)
        if len(target_lang_list):
            task_orgs = task_orgs.filter(target_language__in=target_lang_list)
    if "status" in filter_dict and len(filter_dict["status"]):
        task_orgs = task_orgs.filter(status__in=filter_dict["status"])

    if limit != "All" and limit != "undefined":
        task_orgs = task_orgs[start_offset:end_offset]

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
            completion_time = format_completion_time(time_spent)
        else:
            completion_time = None

        word_count = 0
        word_diff = 0
        word_diff_percent = "-"
        if "Translation" in task.get_task_type_label:
            try:
                trans_cp = Translation.objects.filter(task=task,status="TRANSLATION_EDIT_COMPLETE").first()
                word_count = trans_cp.payload["word_count"]
                payload1 = trans_cp.payload
                trans_ss = Translation.objects.filter(task=task,status="TRANSLATION_SELECT_SOURCE").first()
                payload2 = trans_ss.payload
                payload_len = len(payload2['payload']) if len(payload2['payload']) > len(payload1['payload']) else len(payload1['payload'])
                for seg_no in range(0, payload_len):
                    word_diff += count_word_differences(payload1['payload'][seg_no]['target_text'], payload2['payload'][seg_no]['target_text'])
            except:
                pass
        elif "Transcription" in task.get_task_type_label:
            try:
                trans_cp = Transcript.objects.filter(task=task,status="TRANSCRIPTION_EDIT_COMPLETE").first()
                word_count = trans_cp.payload["word_count"]
                payload1 = trans_cp.payload
                trans_ss = Transcript.objects.filter(task=task,status="TRANSCRIPTION_SELECT_SOURCE").first()
                payload2 = trans_ss.payload
                payload_len = len(payload2['payload']) if len(payload2['payload']) > len(payload1['payload']) else len(payload1['payload'])
                for seg_no in range(1, payload_len):
                    word_diff += count_word_differences(payload1['payload'][seg_no]['text'], payload2['payload'][seg_no]['text'])
            except:
                pass
        elif "VoiceOver" in task.get_task_type_label:
            word_count = "-"
        try:
            word_diff_percent = round(((word_diff / word_count)*100),2)
        except:
            word_diff_percent = 0
        is_active = task.is_active
        tasks_list.append(
            {
                "task_id": {
                    "value": task.id,
                    "label": "Task Id",
                    "viewColumns": False,
                },
                "project_id": {
                    "value": task.video.project_id.id,
                    "label": "Project Id",
                    "viewColumns": False,
                },
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
                "is_active": {
                    "value": str(is_active),
                    "label": "Is Active",
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
                },
                "paraphrasing": {
                    "value": "Enabled" if task.video.project_id.paraphrasing_enabled else "Not Enabled",
                    "label": "Paraphrasing",
                    "viewColumns": False, 
                },
                "word_count": {
                    "value": word_count,
                    "label": "Word Count",
                },
                "changes": {
                    "value": word_diff_percent,
                    "label": "% Changes",
                },
                "created_at": {
                    "value": task.created_at,
                    "label": "Created At",
                },
                "updated_at": {
                    "value": task.updated_at,
                    "label": "Updated At",
                },
            }
        )
    return tasks_list, total_count


def get_org_report_tasks_email(org_id, user, taskStartDate, taskEndDate):
    org = Organization.objects.get(pk=org_id)
    limit = len(Task.objects.filter(video__project_id__organization_id__id=org.id))
    tasks_list, _ = get_org_report_tasks(org_id, user, limit, 1, taskStartDate, taskEndDate)
    columns = [field["label"] for field in tasks_list[0].values()]

    data = [[field["value"] for field in row.values()] for row in tasks_list]
    current_time = datetime.now()

    df = pd.DataFrame(data, columns=columns)
    csv_file_path = "organization_tasks_reports_{}_{}.csv".format(org_id, current_time)
    df.to_csv(csv_file_path, index=False)

    formatted_date = current_time.strftime("%d %b")
    subject = f"Tasks Reports for Organization - {org.title} - {formatted_date}"
    body = "Please find the attached CSV file."
    send_mail_with_report(subject, body, user, [csv_file_path])


def get_org_report_projects(pk, user, limit, offset):
    if limit != "All":
        start_offset = (int(offset) - 1) * int(limit)
        end_offset = start_offset + int(limit)

    all_org_projects = (
        Project.objects.filter(organization_id=pk).values("title", "id").order_by("id")
    )
    total_count = all_org_projects.count()

    if limit != "All":
        org_projects = all_org_projects[start_offset:end_offset]
    else:
        org_projects = all_org_projects

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
            "id": {"value": elem["id"], "label": "Id", "viewColumns": False},
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
    return project_data, total_count


def get_org_report_projects_email(org_id, user):
    org = Organization.objects.get(pk=org_id)
    projects_count = len(Project.objects.filter(organization_id=org.id))
    projects_list, _ = get_org_report_projects(org_id, user, projects_count, 1)
    columns = [field["label"] for field in projects_list[0].values()]

    data = [[field["value"] for field in row.values()] for row in projects_list]
    current_time = datetime.now()

    df = pd.DataFrame(data, columns=columns)
    csv_file_path = "organization_projects_reports_{}_{}.csv".format(
        org_id, current_time
    )
    df.to_csv(csv_file_path, index=False)

    formatted_date = current_time.strftime("%d %b")
    subject = f"Projects Reports for Organization - {org.title} - {formatted_date}"
    body = "Please find the attached CSV file."
    send_mail_with_report(subject, body, user, [csv_file_path])


def paginate_reports(project_users_data, limit):
    project_data = defaultdict(list)
    page_number = 0
    i = 0
    reminder = 0
    end_idx = 0
    while i < len(project_users_data):
        count = 0
        page_number += 1
        while count < limit and i < len(project_users_data):
            if reminder == 0:
                if project_users_data[i][1] <= limit - count:
                    project_data[page_number].append(
                        (
                            project_users_data[i][0],
                            end_idx,
                            end_idx + project_users_data[i][1] - 1,
                        )
                    )
                    count += project_users_data[i][1]
                    i = i + 1
                    reminder = 0
                    end_idx = 0
                else:
                    project_data[page_number].append(
                        (project_users_data[i][0], end_idx, end_idx + limit - count - 1)
                    )
                    reminder = project_users_data[i][1] - (limit - count)
                    end_idx = project_users_data[i][1] - reminder
                    count = limit
            else:
                if reminder <= limit - count:
                    project_data[page_number].append(
                        (project_users_data[i][0], end_idx, end_idx + reminder - 1)
                    )
                    count += reminder
                    i = i + 1
                    reminder = 0
                    end_idx = 0
                else:
                    project_data[page_number].append(
                        (project_users_data[i][0], end_idx, end_idx + limit - count - 1)
                    )
                    reminder = reminder - (limit - count)
                    end_idx = project_users_data[i][1] - reminder
                    count = limit

    return project_data
