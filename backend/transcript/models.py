import uuid
from django.db import models
from translation.metadata import LANGUAGE_CHOICES
from video.models import Video
from task.models import Task
from users.models import User


ORIGINAL_SOURCE = "ORIGINAL_SOURCE"
UPDATED_ORIGINAL_SOURCE = "UPDATED_ORIGINAL_SOURCE"
MACHINE_GENERATED = "MACHINE_GENERATED"
UPDATED_MACHINE_GENERATED = "UPDATED_MACHINE_GENERATED"
MANUALLY_CREATED = "MANUALLY_CREATED"
UPDATED_MANUALLY_CREATED = "UPDATED_MANUALLY_CREATED"
TRANSCRIPTION_SELECT_SOURCE = "TRANSCRIPTION_SELECT_SOURCE"
TRANSCRIPTION_EDITOR_ASSIGNED = "TRANSCRIPTION_EDITOR_ASSIGNED"
TRANSCRIPTION_EDIT_INPROGRESS = "TRANSCRIPTION_EDIT_INPROGRESS"
TRANSCRIPTION_EDIT_COMPLETE = "TRANSCRIPTION_EDIT_COMPLETE"
TRANSCRIPTION_REVIEWER_ASSIGNED = "TRANSCRIPTION_REVIEWER_ASSIGNED"
TRANSCRIPTION_REVIEW_INPROGRESS = "TRANSCRIPTION_REVIEW_INPROGRESS"
TRANSCRIPTION_REVIEW_COMPLETE = "TRANSCRIPTION_REVIEW_COMPLETE"

TRANSCRIPT_TYPE = (
    (ORIGINAL_SOURCE, "Original Source"),
    (MACHINE_GENERATED, "Machine Generated"),
    (MANUALLY_CREATED, "Manually Created"),
)

TRANSCRIPTION_STATUS = (
    (TRANSCRIPTION_SELECT_SOURCE, "Transcription selected source"),
    (TRANSCRIPTION_EDITOR_ASSIGNED, "Transcription Editor Assigned"),
    (TRANSCRIPTION_EDIT_INPROGRESS, "Transcription Edit In-progress"),
    (TRANSCRIPTION_EDIT_COMPLETE, "Transcription Edit Complete"),
    (TRANSCRIPTION_REVIEWER_ASSIGNED, "Transcription Reviewer Assigned"),
    (TRANSCRIPTION_REVIEW_INPROGRESS, "Transcription Review In-progress"),
    (TRANSCRIPTION_REVIEW_COMPLETE, "Transcription Review Complete"),
)


class Transcript(models.Model):
    """
    Model for Transcripts
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        verbose_name="Transcript ID",
    )
    transcript_type = models.CharField(
        choices=TRANSCRIPT_TYPE,
        max_length=35,
        default=MACHINE_GENERATED,
        verbose_name="Transcript Type",
    )
    parent_transcript = models.ForeignKey(
        "self",
        verbose_name="Parent Transcript",
        null=True,
        blank=True,
        default=None,
        on_delete=models.PROTECT,
    )
    video = models.ForeignKey(
        Video,
        on_delete=models.CASCADE,
        verbose_name="Transcript Video ID",
        related_name="transcripts",
    )
    language = models.CharField(
        choices=LANGUAGE_CHOICES,
        max_length=10,
        default="en",
        verbose_name="Transcript Language",
    )
    user = models.ForeignKey(
        User,
        verbose_name="Transcriptor",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    task = models.ForeignKey(
        Task,
        on_delete=models.CASCADE,
        verbose_name="Task id",
        related_name="transcript_tasks",
    )
    status = models.CharField(
        choices=TRANSCRIPTION_STATUS,
        verbose_name="Transcription Status",
        max_length=35,
        default=None,
    )
    payload = models.JSONField(verbose_name="Transcription Output")

    created_at = models.DateTimeField(
        auto_now_add=True, verbose_name="Transcript Created At"
    )
    updated_at = models.DateTimeField(
        auto_now=True, verbose_name="Transcript Updated At"
    )

    def __str__(self):
        return str(self.id)
