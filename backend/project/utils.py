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


def get_reports_for_users(pk):
    project_members = (
        User.objects.filter(projects__pk=pk)
        .filter(has_accepted_invite=True)
        .values(name=Concat("first_name", Value(" "), "last_name"), mail=F("email"))
        .order_by("mail")
    )
    user_statistics = (
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
    word_count_transcript_statistics = (
        project_members.annotate(
            transcript_word_count=Sum(
                Cast(F("transcript__payload__word_count"), FloatField()),
                filter=(
                    Q(transcript__video__project_id=pk)
                    & Q(transcript__status="TRANSCRIPTION_EDIT_COMPLETE")
                ),
            ),
        )
    ).order_by(
        "mail"
    )  # fetching transcript word count
    word_count_translation_statistics = (
        project_members.annotate(
            translation_word_count=Sum(
                Cast(F("translation__payload__word_count"), FloatField()),
                filter=(
                    Q(translation__video__project_id=pk)
                    & Q(translation__status="TRANSLATION_EDIT_COMPLETE")
                ),
            )
        )
    ).order_by(
        "mail"
    )  # fetching translation word count
    user_data = []
    word_count_idx = 0
    for elem in user_statistics:
        while (
            word_count_idx < len(word_count_translation_statistics)
            and elem["name"]
            != word_count_translation_statistics[word_count_idx]["name"]
        ):  # to skip names not present in user_statistics
            word_count_idx += 1
        if word_count_idx >= len(word_count_translation_statistics):
            break
        avg_time = (
            0
            if elem["average_completion_time"] is None
            else round(elem["average_completion_time"] / 3600, 3)
        )
        word_count_translation = (
            0
            if word_count_translation_statistics[word_count_idx][
                "translation_word_count"
            ]
            is None
            else word_count_translation_statistics[word_count_idx][
                "translation_word_count"
            ]
        )
        word_count_transcript = (
            0
            if word_count_transcript_statistics[word_count_idx]["transcript_word_count"]
            is None
            else word_count_transcript_statistics[word_count_idx][
                "transcript_word_count"
            ]
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
                "value": int(word_count_translation + word_count_transcript),
                "label": "Word count",
            },
        }
        user_data.append(user_dict)
    word_count_idx += 1
    return user_data


def send_mail_with_report(project_id, user_data, user):
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

    # Create an EmailMessage object
    subject = f"User Reports for Project - {project.title}"
    body = "Please find the attached CSV file."
    from_email = settings.DEFAULT_FROM_EMAIL
    to_email = user.email
    email = EmailMessage(subject, body, from_email, [to_email])
    # Attach the CSV file to the email
    email.attach_file(csv_file_path)

    # Send the email
    try:
        email.send()
    except:
        logging.info("Unable to send Email.")
    os.remove(csv_file_path)


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
                "label": "Duration (Hours)",
                "viewColumns": False,
            },
            "transcripts_translated": {
                "value": elem["transcripts_translated"],
                "label": "Tasks Count",
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
                "label": "Duration (Hours)",
                "viewColumns": False,
            },
            "voiceovers_completed": {
                "value": elem["voiceovers_completed"],
                "label": "Tasks Count",
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
    user_data = get_reports_for_users(project_id)
    send_mail_with_report(project_id, user_data, user)


def get_project_report_languages_email(project_id, user):
    languages_data = get_reports_for_languages(project_id)
    send_mail_with_languages_report(project_id, language_data, user)
