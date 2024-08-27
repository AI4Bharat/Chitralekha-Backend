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
def send_email_with_tasks_report(org_id, user_id, taskStartDate, taskEndDate):
    user = User.objects.get(pk=user_id)
    get_org_report_tasks_email(org_id, user, taskStartDate, taskEndDate)


@shared_task()
def send_email_with_projects_report(org_id, user_id):
    user = User.objects.get(pk=user_id)
    get_org_report_projects_email(org_id, user)


@shared_task(name="delete_reports")
def delete_reports():
    blob_service_client = BlobServiceClient.from_connection_string(connection_string)
    container_client = blob_service_client.get_container_client(reports_container_name)

    current_date = datetime.now()

    # Calculate one week ago
    one_week_ago = current_date - timedelta(days=7)

    # Convert the specific date to UTC format
    specific_date_utc = datetime.strptime(one_week_ago, "%Y-%m-%d").replace(
        tzinfo=datetime.timezone.utc
    )

    # List all blobs in the container
    blobs = container_client.list_blobs()

    for blob in blobs:
        properties = blob.get_blob_properties()
        last_modified = properties["last_modified"].astimezone(datetime.timezone.utc)

        # Check if the blob was created on the specific date
        if last_modified.date() == specific_date_utc.date():
            blob_client = container_client.get_blob_client(blob.name)
            blob_client.delete_blob()
            print(f"Deleted: {blob.name}")
