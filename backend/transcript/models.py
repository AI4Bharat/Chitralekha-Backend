import uuid

from django.contrib.auth import get_user_model
from django.db import models
from video.models import Video
from .metadata import TRANSCRIPTION_LANGUAGE_CHOICES

ORIGINAL_SOURCE = "os"
UPDATED_ORIGINAL_SOURCE = "uos"
MACHINE_GENERATED = "mg"
UPDATED_MACHINE_GENERATED = "umg"
MANUALLY_CREATED = "mc"

TRANSCRIPT_TYPE = (
    (ORIGINAL_SOURCE, "Original Source"),
    (UPDATED_ORIGINAL_SOURCE, "Updated Original Source"),
    (MACHINE_GENERATED, "Machine Generated"),
    (UPDATED_MACHINE_GENERATED, "Updated Machine Generated"),
    (MANUALLY_CREATED, "Manually Created"),
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
        max_length=10,
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
        choices=TRANSCRIPTION_LANGUAGE_CHOICES,
        max_length=10,
        default="en",
        verbose_name="Transcript Language",
    )
    user = models.ForeignKey(
        get_user_model(),
        verbose_name="Transcriptor",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
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
