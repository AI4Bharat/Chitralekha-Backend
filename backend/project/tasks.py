from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail
from celery.schedules import crontab
from datetime import datetime
from rest_framework.response import Response
from rest_framework import status
from pretty_html_table import build_table


def format_mail(tasks):
    user = list(tasks)[0].user
    message = (
        "Dear "
        + str(user.first_name + " " + user.last_name)
        + ",\n The following tasks are active and not yet started"
        + " are ready.\n Thanks for contributing on Chitralekha!"
    )

    html_table_tasks = build_table(
        df,
        "orange_light",
        font_size="medium",
        text_align="left",
        width="auto",
        index=False,
    )
    email_to_send = "<p>" + message + "</p><br><h>Tasks</h>" + html_table_tasks

    # print(email_to_send)

    send_mail(
        "Daily Annotation Reports",
        message,
        settings.DEFAULT_FROM_EMAIL,
        [annotator.email],
        html_message=email_to_send,
    )


# @shared_task(name="send_mail_task")
@swagger_auto_schema(
    method="get",
    manual_parameters=[
        openapi.Parameter(
            "description",
            openapi.IN_QUERY,
            description=("A string to give description about video"),
            type=openapi.TYPE_STRING,
            required=False,
        )
    ],
    responses={200: "Return the video subtitle payload"},
)
@api_view(["GET"])
def send_mail_task():
    end_time = timezone.now()
    # shift that date by 3 hours to get the start of the range
    start_time = timezone.now() - datetime.timedelta(hours=3)
    # tasks which became active in last 3 hours
    print("end_time>>>>>>>>>>>>>>>>>>>", end_time, start_time)
    tasks = (
        Task.objects.filter(created_at__range=[start_time, end_time])
        .filter(is_active=True)
        .filter(status__in=["NEW", "SELECTED_SOURCE"])
    )
    # users to which, these tasks are assigned
    users = set(tasks.values_list("user", flat=True))
    for user in users:
        print(">>>>>>>>>>>>", user)
        user_wise_tasks = tasks.filter(user=user)
        print("user_wise_tasks", user_wise_tasks)
        format_mail(user_wise_tasks)
    return Response(
        {"message": "Testing."},
        status=status.HTTP_200_OK,
    )
