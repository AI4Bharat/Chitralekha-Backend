import uuid
from django.db import models
from translation.models import Translation
from task.models import Task
from translation.metadata import LANGUAGE_CHOICES
from video.models import Video
from users.models import User


MACHINE_GENERATED = "MACHINE_GENERATED"
MANUALLY_CREATED = "MANUALLY_CREATED"
VOICEOVER_EDITOR_ASSIGNED = "VOICEOVER_EDITOR_ASSIGNED"
VOICEOVER_EDIT_INPROGRESS = "VOICEOVER_EDIT_INPROGRESS"
VOICEOVER_EDIT_COMPLETE = "VOICEOVER_EDIT_COMPLETE"
VOICEOVER_REVIEWER_ASSIGNED = "VOICEOVER_REVIEWER_ASSIGNED"
VOICEOVER_REVIEW_INPROGRESS = "VOICEOVER_REVIEW_INPROGRESS"
VOICEOVER_REVIEW_COMPLETE = "VOICEOVER_REVIEW_COMPLETE"
VOICEOVER_SELECT_SOURCE = "VOICEOVER_SELECT_SOURCE"

VOICEOVER_TYPE_CHOICES = (
    # (MACHINE_GENERATED, "Machine Generated"),
    (MANUALLY_CREATED, "Manually Created"),
)

VOICEOVER_STATUS = (
    (VOICEOVER_SELECT_SOURCE, "Voice Over selected source"),
    (VOICEOVER_EDITOR_ASSIGNED, "Voice Over Editor Assigned"),
    (VOICEOVER_EDIT_INPROGRESS, "Voice Over Edit Inprogress"),
    (VOICEOVER_EDIT_COMPLETE, "Voice Over Edit Complete"),
    (VOICEOVER_REVIEWER_ASSIGNED, "Voice Over Reviewer assigned"),
    (VOICEOVER_REVIEW_INPROGRESS, "Voice Over Review In-progress"),
    (VOICEOVER_REVIEW_COMPLETE, "Voice Over Review Complete"),
)


class VoiceOver(models.Model):
    """
    Voice Over model
    """

    voice_over_uuid = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
        verbose_name="Voice Over UUID",
        primary_key=False,
    )
    voice_over_type = models.CharField(
        choices=VOICEOVER_TYPE_CHOICES, max_length=35, verbose_name="Voice Over Type"
    )
    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        default=None,
        on_delete=models.CASCADE,
        verbose_name="Parent Voice Over",
    )
    translation = models.ForeignKey(
        Translation,
        on_delete=models.CASCADE,
        verbose_name="Voice Over Transcript",
        related_name="voice_overs",
        null=True,
    )
    user = models.ForeignKey(
        User,
        verbose_name="Speaker",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    status = models.CharField(
        choices=VOICEOVER_STATUS,
        verbose_name="Voice Over Status",
        max_length=35,
        default=None,
    )
    payload = models.JSONField(verbose_name="Voice Over Output", null=True)
    video = models.ForeignKey(
        Video,
        on_delete=models.CASCADE,
        verbose_name="Voice Over Video ID",
        related_name="voice_over_video",
    )
    target_language = models.CharField(
        choices=LANGUAGE_CHOICES, max_length=4, verbose_name="Target Language"
    )
    task = models.ForeignKey(
        Task,
        on_delete=models.CASCADE,
        verbose_name="Task id",
        related_name="voice_over_tasks",
    )
    created_at = models.DateTimeField(
        auto_now_add=True, verbose_name="Voice Over Created At"
    )
    updated_at = models.DateTimeField(
        auto_now=True, verbose_name="Voice Over Updated At"
    )

    def __str__(self):
        return "Voice Over: " + str(self.voice_over_uuid)
