from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail
from celery.schedules import crontab
from backend.celery import celery_app
from user_reports import *


@shared_task(name="send_completed_tasks_mail")
def send_completed_tasks_mail():
    get_completed_tasks()


@shared_task(name="send_new_tasks_mail")
def send_new_tasks_mail():
    get_new_tasks()
