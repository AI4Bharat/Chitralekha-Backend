from django.db import models
import uuid
from project.models import Project
from translation.metadata import LANGUAGE_CHOICES


class Video(models.Model):
    """
    Model for the Video object.
    """

    video_uuid = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
        verbose_name="Video UUID",
        primary_key=False,
    )
    name = models.CharField(max_length=255, verbose_name="Video Name")
    url = models.URLField(unique=True, verbose_name="Video URL", db_index=True)
    project_id = models.ForeignKey(
        Project,
        on_delete=models.SET_NULL,
        null=True,
        help_text=("Organization to which the Project belongs"),
    )
    language = models.CharField(
        choices=LANGUAGE_CHOICES, max_length=4, verbose_name="Target Language"
    )
    duration = models.DurationField(verbose_name="Video Duration")
    subtitles = models.JSONField(verbose_name="Subtitles", null=True, blank=True)
    audio_only = models.BooleanField(
        verbose_name="Audio Only",
        default=False,
        help_text="Does this object only contain audio?",
    )

    def __str__(self):
        return str(self.video_uuid) + " : " + self.name
