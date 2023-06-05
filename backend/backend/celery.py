import os
from celery import Celery
from celery.schedules import crontab


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings")
app = Celery(
    "backend",
    accept_content=["application/json"],
    result_serializer="json",
    task_serializer="json",
    worker_prefetch_multiplier=0,
)
app.config_from_object("django.conf:settings", namespace="CELERY")

# Celery Queue related settings
app.conf.task_default_queue = "default"
app.conf.task_routes = {"task.tasks.*": {"queue": "task"}}
app.conf.task_routes = {"transcript.tasks.*": {"queue": "ytt"}}

app.conf.beat_schedule = {
    "Send_mail_to_managers_completed": {
        "task": "send_completed_tasks_mail",
        "schedule": crontab(minute=0, hour="*/6"),  # execute 4 times in a day
    },
    "Send_mail_to_managers_new": {
        "task": "send_new_tasks_mail",
        "schedule": crontab(minute=0, hour=1),  # execute everyday at 1 am
    },
}


app.autodiscover_tasks()
