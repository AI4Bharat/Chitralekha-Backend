import os
from celery import Celery

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
app.autodiscover_tasks()
