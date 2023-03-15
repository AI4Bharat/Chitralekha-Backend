from django.db import models
import uuid
from project.models import Project
from translation.metadata import LANGUAGE_CHOICES
from django.contrib.postgres.fields import ArrayField

MALE = "MALE"
FEMALE = "FEMALE"

VIDEO_STATUS = (
    ("NEW", "NEW"),
    ("TRANSCRIPTION_EDIT", "Transcription Edit"),
    ("TRANSCRIPTION_REVIEW", "Transcription Review"),
    ("TRANSLATION_EDIT", "Translation Edit"),
    ("TRANSLATION_REVIEW", "Translation Review"),
    ("COMPLETED", "COMPLETED"),
)

GENDER = ((MALE, "Male"), (FEMALE, "Female"))


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
    url = models.URLField(verbose_name="Video URL", db_index=True)
    project_id = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        help_text=("Organization to which the Project belongs"),
    )
    language = models.CharField(
        choices=LANGUAGE_CHOICES, max_length=4, verbose_name="Target Language"
    )
    description = models.TextField(
        max_length=400, null=True, blank=True, help_text=("Video Description")
    )
    duration = models.DurationField(verbose_name="Video Duration")
    subtitles = models.JSONField(verbose_name="Subtitles", null=True, blank=True)
    audio_only = models.BooleanField(
        verbose_name="Audio Only",
        default=False,
        help_text="Does this object only contain audio?",
    )
    gender = models.CharField(
        choices=GENDER,
        max_length=10,
        default=MALE,
        null=True,
        blank=True,
        verbose_name="Gender",
    )

    def __str__(self):
        return str(self.video_uuid) + " : " + self.name

    @property
    def get_language_label(self):
        for language in LANGUAGE_CHOICES:
            if self.language == language[0]:
                return language[1]

    def get_gender_label(gender):
        for gender_list_obj in GENDER:
            if gender == gender_list_obj[1]:
                return gender_list_obj[0]
