from .models import Project
from celery import shared_task
import logging
import pandas as pd
import datetime
from django.core.mail import send_mail, EmailMessage
from .utils import get_project_report_users_email, get_project_report_languages_email
from users.models import User


@shared_task()
def send_email_with_users_report(project_id, user_id):
    user = User.objects.get(pk=user_id)
    get_project_report_users_email(project_id, user)


@shared_task()
def send_email_with_languages_report(project_id, user_id):
    user = User.objects.get(pk=user_id)
    get_project_report_languages_email(project_id, user)
