import uuid
from django.db import models
from transcript.models import Transcript
from task.models import Task
from .metadata import TRANSLATION_LANGUAGE_CHOICES
from video.models import Video
from users.models import User


UPDATED_MACHINE_GENERATED = "UPDATED_MACHINE_GENERATED"
MACHINE_GENERATED = "MACHINE_GENERATED"
MANUALLY_CREATED = "MANUALLY_CREATED"
ORIGINAL_SOURCE = "ORIGINAL_SOURCE"
UPDATED_MANUALLY_CREATED = "UPDATED_MANUALLY_CREATED"
TRANSLATION_EDITOR_ASSIGNED = "TRANSLATION_EDITOR_ASSIGNED"
TRANSLATION_EDIT_INPROGRESS = "TRANSLATION_EDIT_INPROGRESS"
TRANSLATION_EDIT_COMPLETE = "TRANSLATION_EDIT_COMPLETE"
TRANSLATION_REVIEWER_ASSIGNED = "TRANSLATION_REVIEWER_ASSIGNED"
TRANSLATION_REVIEW_INPROGRESS = "TRANSLATION_REVIEW_INPROGRESS"
TRANSLATION_REVIEW_COMPLETE = "TRANSLATION_REVIEW_COMPLETE"
TRANSLATION_SELECT_SOURCE = "TRANSLATION_SELECT_SOURCE"

TRANSLATION_TYPE_CHOICES = (
    (MACHINE_GENERATED, "Machine Generated"),
    (MANUALLY_CREATED, "Manually Created"),
    # (ORIGINAL_SOURCE, "Original Source"),
)

TRANSLATION_STATUS = (
    (TRANSLATION_SELECT_SOURCE, "Translation selected source"),
    (TRANSLATION_EDITOR_ASSIGNED, "Translation Editor Assigned"),
    (TRANSLATION_EDIT_INPROGRESS, "Translation Edit Inprogress"),
    (TRANSLATION_EDIT_COMPLETE, "Translation Edit Complete"),
    (TRANSLATION_REVIEWER_ASSIGNED, "Translation Reviewer assigned"),
    (TRANSLATION_REVIEW_INPROGRESS, "Translation Review In-progress"),
    (TRANSLATION_REVIEW_COMPLETE, "Translation Review Complete"),
)


class Translation(models.Model):
    """
    Translation model
    """

    translation_uuid = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
        verbose_name="Translation UUID",
        primary_key=False,
    )
    translation_type = models.CharField(
        choices=TRANSLATION_TYPE_CHOICES, max_length=35, verbose_name="Translation Type"
    )
    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        default=None,
        on_delete=models.CASCADE,
        verbose_name="Parent Translation",
    )
    transcript = models.ForeignKey(
        Transcript,
        on_delete=models.CASCADE,
        verbose_name="Translation Transcript",
        related_name="translations",
        null=True,
    )

    target_language = models.CharField(
        choices=TRANSLATION_LANGUAGE_CHOICES,
        max_length=4,
        verbose_name="Target Language",
    )
    user = models.ForeignKey(
        User,
        verbose_name="Translator",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    status = models.CharField(
        choices=TRANSLATION_STATUS,
        verbose_name="Translation Status",
        max_length=35,
        default=None,
    )
    payload = models.JSONField(verbose_name="Translation Output", null=True)
    video = models.ForeignKey(
        Video,
        on_delete=models.CASCADE,
        verbose_name="Translation Video ID",
        related_name="translation_video",
    )
    task = models.ForeignKey(
        Task,
        on_delete=models.CASCADE,
        verbose_name="Task id",
        related_name="translation_tasks",
    )
    created_at = models.DateTimeField(
        auto_now_add=True, verbose_name="Translation Created At"
    )
    updated_at = models.DateTimeField(
        auto_now=True, verbose_name="Translation Updated At"
    )

    def __str__(self):
        return "Translation: " + str(self.translation_uuid)
