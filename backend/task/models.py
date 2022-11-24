import uuid
from django.contrib.auth import get_user_model
from django.db import models
from translation.metadata import LANGUAGE_CHOICES
from video.models import Video
from django.conf import settings

TRANSCRIPTION_SELECT_SOURCE = "TRANSCRIPTION_SELECT_SOURCE"
TRANSCRIPTION_EDIT = "TRANSCRIPTION_EDIT"
TRANSCRIPTION_REVIEW = "TRANSCRIPTION_REVIEW"
TRANSLATION_SELECT_SOURCE = "TRANSLATION_SELECT_SOURCE"
TRANSLATION_EDIT = "TRANSLATION_EDIT"
TRANSLATION_REVIEW = "TRANSLATION_REVIEW"
NEW = "NEW"
INPROGRESS = "INPROGRESS"
COMPLETE = "COMPLETE"

TASK_STATUS = (
    (NEW, "NEW"),
    (INPROGRESS, "INPROGRESS"),
    (COMPLETE, "COMPLETE"),
)

TASK_TYPE = (
    (TRANSCRIPTION_EDIT, "Transcription Edit"),
    (TRANSCRIPTION_REVIEW, "Transcription Review"),
    (TRANSLATION_EDIT, "Translation Edit"),
    (TRANSLATION_REVIEW, "Translation Review"),
    (TRANSCRIPTION_SELECT_SOURCE, "Transcription Select Source"),
    (TRANSLATION_SELECT_SOURCE, "Translation Select Source"),
)


class Task(models.Model):
    """
    Model for Tasks
    """

    task_uuid = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
        verbose_name="Task UUID",
        primary_key=False,
    )
    task_type = models.CharField(
        choices=TASK_TYPE,
        max_length=35
    )
    video = models.ForeignKey(
        Video,
        on_delete=models.CASCADE,
        verbose_name="Task Video ID",
        related_name="tasks",
    )
    target_language = models.CharField(
        choices=LANGUAGE_CHOICES, max_length=4, verbose_name="Target Language", blank=True
    )
    status = models.CharField(
        choices=TASK_STATUS, verbose_name="Task Status", max_length=35, default=None
    )
    user = models.ForeignKey(
        get_user_model(),
        verbose_name="Task Assignee",
        on_delete=models.CASCADE,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name="task_created",
        verbose_name="created_by",
        help_text=("Task Created By"),
    )

    def __str__(self):
        return str(self.id)
