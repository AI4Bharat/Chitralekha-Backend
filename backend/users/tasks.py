from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail
from celery.schedules import crontab
from backend.celery import celery_app
from user_reports import *
from organization.models import Organization
from .models import User


@shared_task(name="send_completed_tasks_mail")
def send_completed_tasks_mail():
    get_completed_tasks()

@shared_task(name="send_active_tasks_mail")
def send_active_tasks_mail():
    get_active_tasks()

@shared_task(name="send_new_tasks_mail")
def send_new_tasks_mail():
    get_new_tasks()


@shared_task(name="send_new_users_to_org_owner")
def send_new_users_to_org_owner():
    get_new_users()


@shared_task(name="send_eta_reminders")
def send_eta_reminders():
    get_eta_reminders()
