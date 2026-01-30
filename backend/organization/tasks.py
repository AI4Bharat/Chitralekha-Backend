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
from utils.storage_factory import get_storage_provider
from datetime import datetime, timedelta, timezone


@shared_task()
def send_email_with_users_report(org_id, user_id):
    user = User.objects.get(pk=user_id)
    get_org_report_users_email(org_id, user)


@shared_task()
def send_email_with_languages_report(org_id, user_id):
    user = User.objects.get(pk=user_id)
    get_org_report_languages_email(org_id, user)


@shared_task()
def send_email_with_tasks_report(org_id, user_id, taskStartDate, taskEndDate):
    user = User.objects.get(pk=user_id)
    get_org_report_tasks_email(org_id, user, taskStartDate, taskEndDate)


@shared_task()
def send_email_with_projects_report(org_id, user_id):
    user = User.objects.get(pk=user_id)
    get_org_report_projects_email(org_id, user)


@shared_task(name="delete_reports")
def delete_reports():
    storage = get_storage_provider(reports_container=True)
    
    one_week_ago_date = (datetime.now(timezone.utc) - timedelta(days=7)).date()

    objects = storage.list_objects()

    for obj in objects:
        if obj.last_modified.date() == one_week_ago_date:
            storage.delete(obj.name)
            print(f"Deleted: {obj.name}")