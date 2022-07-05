from django.db import models
import uuid

from django.contrib.auth.models import User
from video.models import Video

MACHINE_GENERATED = "machine_generated"
HUMAN_EDITED = "human_edited"
MANUALLY_CREATED = "manually_created"
ORIGINAL_SOURCE = "original_source"

TRANSCRIPT_TYPE = (
    (MACHINE_GENERATED, "machine_generated"),
    (HUMAN_EDITED, "human_edited"),
    (MANUALLY_CREATED, "manually_created"),
    (ORIGINAL_SOURCE, "original_source"),
)

LANGUAGE_CHOICES = (
    ("English", "English"),
    ("Hindi", "Hindi"),
)

class Transcript(models.Model):
    """
    Model for Transcripts
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, verbose_name="transcript_id")
    transcript_type = models.CharField(choices=TRANSCRIPT_TYPE, max_length=50, default=MACHINE_GENERATED, verbose_name="transcript_type")
    parent_transcript = models.ForeignKey(
        'self', verbose_name='parent_transcript', null=True, blank=True, default=None, on_delete=models.PROTECT
    )
    video = models.ForeignKey(
        Video, on_delete=models.CASCADE, verbose_name="transcript_video_id", related_name="transcripts"
    )
    language = models.CharField(choices=LANGUAGE_CHOICES, max_length=50, default="English", verbose_name="transcription_language")
    user = models.ForeignKey(User, verbose_name="transcriptor", null=True, blank=True, on_delete=models.SET_NULL)
    payload = models.JSONField(verbose_name="transcription_output")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="transcription_created_at")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="transcription_updated_at")

    def __str__(self):
        return str(self.id)