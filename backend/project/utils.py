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


def get_project_report_users_email(project_id, user):
    user_data = get_reports_for_users(project_id)
    send_mail_with_report(project_id, user_data, user)
