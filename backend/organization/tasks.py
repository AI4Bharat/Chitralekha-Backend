from celery import shared_task
import logging
import pandas as pd
import datetime
from django.core.mail import send_mail, EmailMessage
from .utils import (
    get_org_report_users_email,
    get_org_report_languages_email,
    get_org_report_tasks_email,
    get_org_report_projects_email,
)
from users.models import User
from azure.storage.blob import BlobServiceClient
from datetime import datetime, timedelta
from config import storage_account_key, connection_string, reports_container_name


@shared_task()
def send_email_with_users_report(org_id, user_id):
    user = User.objects.get(pk=user_id)
    get_org_report_users_email(org_id, user)


@shared_task()
def send_email_with_languages_report(org_id, user_id):
    user = User.objects.get(pk=user_id)
    get_org_report_languages_email(org_id, user)


@shared_task()
def send_email_with_tasks_report(org_id, user_id):
    user = User.objects.get(pk=user_id)
    get_org_report_tasks_email(org_id, user)


@shared_task()
def send_email_with_projects_report(org_id, user_id):
    user = User.objects.get(pk=user_id)
    get_org_report_projects_email(org_id, user)
