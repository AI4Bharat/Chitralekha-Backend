
import uuid
from django.db import models
from transcript.models import Transcript
from task.models import Task
from .metadata import (
    TRANSLATION_LANGUAGE_CHOICES,
    VOICEOVER_LANGUAGE_CHOICES,
)

TRANSLATION_VOICEOVER_STATUS_CHOICES = (
    ("SELECT_SOURCE", "Selected Source"),
    ("EDITOR_ASSIGNED", "Editor Assigned"),
    ("EDIT_INPROGRESS", "Edit In Progress"),
    ("EDIT_COMPLETE", "Edit Complete"),
    ("REVIEWER_ASSIGNED", "Reviewer Assigned"),
    ("REVIEW_INPROGRESS", "Review In Progress"),
    ("REVIEW_COMPLETE", "Review Complete"),
)

TRANSLATION_VOICEOVER_TYPE_CHOICES = (
    ("MACHINE_GENERATED", "Machine Generated"),
    ("MANUALLY_CREATED", "Manually Created"),
)

class TranslationVoiceover(models.Model):
    """
    Combined Translation and Voiceover model
    """

    translation_voiceover_uuid = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
        verbose_name="Translation Voiceover UUID",
    )
    translation_type = models.CharField(
        choices=TRANSLATION_VOICEOVER_TYPE_CHOICES,
        max_length=35,
        verbose_name="Translation Type",
    )

    #!Finalize on type
    voiceover_type = models.CharField(
        choices=TRANSLATION_VOICEOVER_TYPE_CHOICES,
        max_length=35,
        verbose_name="Voiceover Type",
    )
    #!Finalize on type
    transcript = models.ForeignKey(
        Transcript,
        on_delete=models.CASCADE,
        verbose_name="Transcript",
        related_name="translation_voiceovers",
        null=True,
    )
    user = models.ForeignKey(
        User,
        verbose_name="Speaker/Translator",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    status = models.CharField(
        choices=TRANSLATION_VOICEOVER_STATUS_CHOICES,
        verbose_name="Status",
        max_length=35,
        default=None,
    )
    translation_payload = models.JSONField(
        verbose_name="Translation Payload", null=True
    )
    voiceover_payload = models.JSONField(
        verbose_name="Voiceover Payload", null=True
    )
    video = models.ForeignKey(
        Video,
        on_delete=models.CASCADE,
        verbose_name="Video",
        related_name="translation_voiceovers",
    )
    target_language = models.CharField(
        choices=TRANSLATION_LANGUAGE_CHOICES + VOICEOVER_LANGUAGE_CHOICES,
        max_length=4,
        verbose_name="Target Language",
    )
    #! How to reconcile this
    task = models.ForeignKey(
        Task,
        on_delete=models.CASCADE,
        verbose_name="Task",
        related_name="translation_voiceovers",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    voiceover_azure_url = models.URLField(
        max_length=200, verbose_name="Azure URL", default=None, blank=True, null=True
    )
    voiceover_azure_url_audio = models.URLField(
        max_length=200, verbose_name="Azure Audio URL", default=None, blank=True, null=True
    )

    def __str__(self):
        return f"TranslationVoiceover: {self.translation_voiceover_uuid}"
