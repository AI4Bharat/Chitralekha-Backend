from users.models import User
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
from django.db.models.functions import Cast, Concat, Extract
from datetime import timedelta, datetime
import pandas as pd
from project.models import Project
from django.conf import settings
from django.core.mail import send_mail, EmailMessage
import logging
import os
from translation.metadata import TRANSLATION_LANGUAGE_CHOICES
from voiceover.metadata import VOICEOVER_LANGUAGE_CHOICES
from transcript.models import Transcript
from translation.models import Translation
from voiceover.models import VoiceOver
from video.models import Video
from azure.storage.blob import BlobServiceClient
from config import storage_account_key, connection_string, reports_container_name
from django.conf import settings


def get_language_label(target_language):
    for language in TRANSLATION_LANGUAGE_CHOICES:
        if target_language == language[1]:
            return language[0]
    return "-"

def count_word_differences(text1, text2):
    words1 = set(text1.split())
    words2 = set(text2.split())
    return len(words1.symmetric_difference(words2))

def get_reports_for_users(pk, start, end):
    subquery = (
        User.objects.filter(projects__pk=pk, has_accepted_invite=True)
        .order_by("email")
        .values("id")
    )

    project_members = (
        User.objects.filter(id__in=subquery)
        .values(name=Concat("first_name", Value(" "), "last_name"), mail=F("email"))
        .order_by("mail")
    )

    all_user_statistics = (
        project_members.annotate(
            tasks_assigned_count=Count("task", filter=Q(task__video__project_id=pk))
        )
        .annotate(
            tasks_completed_count=Count(
                "task",
                filter=Q(task__status="COMPLETE") & Q(task__video__project_id=pk),
            )
        )
        .annotate(
            task_completion_percentage=Cast(F("tasks_completed_count"), FloatField())
            / Cast(F("tasks_assigned_count"), FloatField())
            * 100
        )
        .annotate(
            average_completion_time=Avg(
                Case(
                    When(
                        (
                            Q(task__status="COMPLETE")
                            & Q(task__updated_at__lt=(datetime(2023, 4, 5, 17, 0, 0)))
                        ),
                        then=(
                            Extract(
                                F("task__updated_at") - F("task__created_at"),
                                "epoch",
                            )
                        ),
                    ),
                    When(
                        (
                            Q(task__status="COMPLETE")
                            & Q(task__updated_at__gte=(datetime(2023, 4, 5, 17, 0, 0)))
                        ),
                        then=F("task__time_spent"),
                    ),
                    default=0,
                    output_field=IntegerField(),
                ),
                filter=Q(task__status="COMPLETE"),
            )
        )
        .exclude(tasks_assigned_count=0)
    ).order_by("mail")
    total_count = len(all_user_statistics)
    user_statistics = all_user_statistics[start:end]

    user_data = []

    for elem in user_statistics:
        transcript_word_count = User.objects.filter(
            transcript__video__project_id__id=pk,
            transcript__status="TRANSCRIPTION_EDIT_COMPLETE",
            transcript__task__user__email=elem["mail"],
        ).aggregate(
            transcript_word_count=Sum(
                Cast("transcript__payload__word_count", FloatField())
            )
        )

        user_transcription_complete_payloads = User.objects.filter(
            transcript__video__project_id__id=pk,
            transcript__status="TRANSCRIPTION_EDIT_COMPLETE",
            transcript__task__user__email=elem["mail"],
        ).values_list("transcript__video", "transcript__payload")
        transcription_complete_payloads = {video_id: payload["payload"] for video_id, payload in user_transcription_complete_payloads if "payload" in payload}
        user_transcription_selectsource_payloads = User.objects.filter(
            transcript__video__project_id__id=pk,
            transcript__status="TRANSCRIPTION_SELECT_SOURCE",
            transcript__task__user__email=elem["mail"],
        ).values_list("transcript__video", "transcript__payload")
        transcription_selectsource_payloads = {video_id: payload["payload"] for video_id, payload in user_transcription_selectsource_payloads if "payload" in payload}

        transcript_word_diff = 0
        for video_id, payload1 in transcription_complete_payloads.items():
            try:
                payload2 = transcription_selectsource_payloads[video_id]
                payload_len = len(payload2) if len(payload2) > len(payload1) else len(payload1)
                for seg_no in range(0, payload_len):
                    transcript_word_diff += count_word_differences(payload1[seg_no]['text'], payload2[seg_no]['text'])
            except:
                continue

        transcript_result = (
            transcript_word_count["transcript_word_count"]
            if transcript_word_count["transcript_word_count"] is not None
            else 0.0
        )

        translation_word_count = User.objects.filter(
            translation__video__project_id__id=pk,
            translation__status="TRANSLATION_EDIT_COMPLETE",
            translation__task__user__email=elem["mail"],
        ).aggregate(
            translation_word_count=Sum(
                Cast("translation__payload__word_count", FloatField())
            )
        )

        user_translation_complete_payloads = User.objects.filter(
            translation__video__project_id__id=pk,
            translation__status="TRANSLATION_EDIT_COMPLETE",
            translation__task__user__email=elem["mail"],
        ).values_list("translation__video", "translation__payload")
        translation_complete_payloads = {video_id: payload["payload"] for video_id, payload in user_translation_complete_payloads if "payload" in payload}
        user_translation_selectsource_payloads = User.objects.filter(
            translation__video__project_id__id=pk,
            translation__status="TRANSLATION_SELECT_SOURCE",
            translation__task__user__email=elem["mail"],
        ).values_list("translation__video", "translation__payload")
        translation_selectsource_payloads = {video_id: payload["payload"] for video_id, payload in user_translation_selectsource_payloads if "payload" in payload}

        translation_word_diff = 0
        for video_id, payload1 in translation_complete_payloads.items():
            try:
                payload2 = translation_selectsource_payloads[video_id]
                payload_len = len(payload2) if len(payload2) > len(payload1) else len(payload1)
                for seg_no in range(0, payload_len):
                    translation_word_diff += count_word_differences(payload1[seg_no]['target_text'], payload2[seg_no]['target_text'])
            except:
                continue

        translation_result = (
            translation_word_count["translation_word_count"]
            if translation_word_count["translation_word_count"] is not None
            else 0.0
        )
        elem["word_count_translation"] = int(translation_result)
        elem["word_count_transcript"] = int(transcript_result)
        try:
            elem["word_diff_percent"] = round(((int(translation_word_diff) + int(transcript_word_diff)) / (int(transcript_result) + int(translation_result))) * 100, 2)
        except:
            elem["word_diff_percent"] = "-"
        avg_time = (
            0
            if elem["average_completion_time"] is None
            else round(elem["average_completion_time"] / 3600, 3)
        )
        user_dict = {
            "name": {"value": elem["name"], "label": "Name", "viewColumns": False},
            "mail": {"value": elem["mail"], "label": "Email", "viewColumns": False},
            "tasks_assigned_count": {
                "value": elem["tasks_assigned_count"],
                "label": "Assigned Tasks",
            },
            "tasks_completed_count": {
                "value": elem["tasks_completed_count"],
                "label": "Completed Tasks",
            },
            "tasks_completion_perc": {
                "value": round(elem["task_completion_percentage"], 2),
                "label": "Task Completion Index(%)",
            },
            "avg_comp_time": {
                "value": float("{:.2f}".format(avg_time)),
                "label": "Avg. Completion Time (Hours)",
            },
            "word_count": {
                "value": elem["word_count_translation"] + elem["word_count_transcript"],
                "label": "Word count",
            },
            "changes": {
                "value": elem["word_diff_percent"],
                "label": "% Changes",
            },
        }
        user_data.append(user_dict)
    return user_data, total_count


def send_mail_with_report(subject, body, user, csv_file_paths):
    blob_service_client = BlobServiceClient.from_connection_string(connection_string)
    report_urls = []

    for file_path in csv_file_paths:
        blob_client = blob_service_client.get_blob_client(
            container=reports_container_name, blob=file_path
        )
        with open(file_path, "rb") as data:
            try:
                if not blob_client.exists():
                    blob_client.upload_blob(data)
                    logging.info("Report uploaded successfully!")
                    logging.info(blob_client.url)
                else:
                    blob_client.delete_blob()
                    logging.info("Old Report deleted successfully!")
                    blob_client.upload_blob(data)
                    logging.info("New Report uploaded successfully!")
            except Exception as e:
                logging.info("This report can't be uploaded")
        report_urls.append(blob_client.url)

    if len(report_urls) == 1:
        try:
            reports_message = """<p>The requested report has been successfully generated. <br><br><a href={url} target="_blank">Click Here</a> to access the reports.</p>""".format(
                url=report_urls[0]
            )
            send_mail(
                subject,
                "",
                settings.DEFAULT_FROM_EMAIL,
                [user.email],
                html_message=reports_message,
            )
        except:
            logging.info("Email Can't be sent.")
    else:
        try:
            reports_msg = """<p>The requested report has been successfully generated. <br><br><a href={url_1} target="_blank">Click Here</a> to access the Transcription reports.<br><br><a href={url_2} target="_blank">Click Here</a> to access the Translation reports.<br><br><a href={url_3} target="_blank">Click Here</a> to access the VoiceOver reports.</p>""".format(
                url_1=report_urls[0], url_2=report_urls[1], url_3=report_urls[2]
            )
            send_mail(
                subject,
                "",
                settings.DEFAULT_FROM_EMAIL,
                [user.email],
                html_message=reports_msg,
            )
        except:
            logging.info("Email Can't be sent.")

    for file_path in csv_file_paths:
        os.remove(file_path)


def get_reports_for_languages(pk):
    prj_videos = Video.objects.filter(project_id=pk)
    prj_transcriptions = (
        Transcript.objects.filter(video__in=prj_videos)
        .filter(status="TRANSCRIPTION_EDIT_COMPLETE")
        .values("language")
    )
    transcript_statistics = (
        prj_transcriptions.annotate(transcripts=Count("id"))
        .annotate(total_duration=Sum(F("video__duration")))
        .annotate(word_count=Sum(Cast(F("payload__word_count"), FloatField())))
        .order_by("-total_duration")
    )
    prj_translations = (
        Translation.objects.filter(video__in=prj_videos)
        .filter(status="TRANSLATION_EDIT_COMPLETE")
        .values(src_language=F("video__language"), tgt_language=F("target_language"))
    )
    translation_statistics = (
        prj_translations.annotate(transcripts_translated=Count("id"))
        .annotate(translation_duration=Sum(F("video__duration")))
        .annotate(word_count=Sum(Cast(F("payload__word_count"), FloatField())))
        .order_by("-translation_duration")
    )
    prj_voiceovers = (
        VoiceOver.objects.filter(video__in=prj_videos)
        .filter(status="VOICEOVER_EDIT_COMPLETE")
        .values(src_language=F("video__language"), tgt_language=F("target_language"))
    )
    voiceover_statistics = (
        prj_voiceovers.annotate(voiceovers_completed=Count("id"))
        .annotate(voiceover_duration=Sum(F("video__duration")))
        .order_by("-voiceover_duration")
    )

    transcript_data = []
    for elem in transcript_statistics:
        transcript_dict = {
            "language": {
                "value": dict(TRANSLATION_LANGUAGE_CHOICES)[elem["language"]],
                "label": "Source Language",
                "viewColumns": False,
            },
            "total_duration": {
                "value": round(elem["total_duration"].total_seconds() / 3600, 3),
                "label": "Duration (Hours)",
                "viewColumns": False,
            },
            "transcripts": {
                "value": elem["transcripts"],
                "label": "Tasks Count",
            },
            "word_count": {
                "value": elem["word_count"],
                "label": "Word Count",
            },
        }
        transcript_data.append(transcript_dict)

    translation_data = []
    for elem in translation_statistics:
        translation_dict = {
            "src_language": {
                "value": dict(TRANSLATION_LANGUAGE_CHOICES)[elem["src_language"]],
                "label": "Source Langauge",
                "viewColumns": False,
            },
            "tgt_language": {
                "value": dict(TRANSLATION_LANGUAGE_CHOICES)[elem["tgt_language"]],
                "label": "Target Language",
                "viewColumns": False,
            },
            "translation_duration": {
                "value": round(elem["translation_duration"].total_seconds() / 3600, 3),
                "label": "Translation Duration (Hours)",
                "viewColumns": False,
            },
            "transcripts_translated": {
                "value": elem["transcripts_translated"],
                "label": "Translation Tasks Count",
            },
            "word_count": {
                "value": elem["word_count"],
                "label": "Word Count",
            },
        }
        translation_data.append(translation_dict)

    voiceover_data = []
    for elem in voiceover_statistics:
        voiceover_dict = {
            "src_language": {
                "value": dict(VOICEOVER_LANGUAGE_CHOICES)[elem["src_language"]],
                "label": "Source Language",
                "viewColumns": False,
            },
            "tgt_language": {
                "value": dict(VOICEOVER_LANGUAGE_CHOICES)[elem["tgt_language"]],
                "label": "Target Language",
                "viewColumns": False,
            },
            "voiceover_duration": {
                "value": round(elem["voiceover_duration"].total_seconds() / 3600, 3),
                "label": "Voiceover Duration (Hours)",
                "viewColumns": False,
            },
            "voiceovers_completed": {
                "value": elem["voiceovers_completed"],
                "label": "Voiceover Tasks Count",
            },
        }
        voiceover_data.append(voiceover_dict)
    res = {
        "transcript_stats": transcript_data,
        "translation_stats": translation_data,
        "voiceover_stats": voiceover_data,
    }
    return res


def get_project_report_users_email(project_id, user):
    start = 0
    end = len(User.objects.filter(projects__pk=project_id, has_accepted_invite=True))
    user_data, _ = get_reports_for_users(project_id, start, end)
    project = Project.objects.get(pk=project_id)
    columns = [field["label"] for field in user_data[0].values()]

    # Extract data values from the 'value' field of each dictionary
    data = [[field["value"] for field in row.values()] for row in user_data]
    current_time = datetime.now()

    # Create a DataFrame
    df = pd.DataFrame(data, columns=columns)
    csv_file_path = "project_user_reports_{}_{}.csv".format(project_id, current_time)
    # Write DataFrame to a CSV file
    df.to_csv(csv_file_path, index=False)

    formatted_date = current_time.strftime("%d %b")
    subject = f"User Reports for Project - {project.title} - {formatted_date}"
    body = "Please find the attached CSV file."
    send_mail_with_report(subject, body, user, [csv_file_path])


def get_project_report_languages_email(project_id, user):
    project = Project.objects.get(pk=project_id)
    data = get_reports_for_languages(project_id)

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
    # Write CSV files using pandas
    write_csv_pandas(
        "transcript_stats_{}_{}.csv".format(project_id, current_time),
        data["transcript_stats"],
    )
    write_csv_pandas(
        "translation_stats_{}_{}.csv".format(project_id, current_time),
        data["translation_stats"],
    )
    write_csv_pandas(
        "voiceover_stats_{}_{}.csv".format(project_id, current_time),
        data["voiceover_stats"],
    )

    formatted_date = current_time.strftime("%d %b")
    subject = f"Languages Reports for Project - {project.title} - {formatted_date}"
    body = "Please find the attached CSV file."
    send_mail_with_report(subject, body, user, csv_file_paths)


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
