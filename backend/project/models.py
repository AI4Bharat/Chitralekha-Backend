from django.db import models
from django.conf import settings
from organization.models import Organization
from translation.metadata import TRANSLATION_LANGUAGE_CHOICES
from django.contrib.postgres.fields import ArrayField

TRANSCRIPT_TYPE = (
    ("ORIGINAL_SOURCE", "Original Source"),
    ("MACHINE_GENERATED", "Machine Generated"),
    ("MANUALLY_CREATED", "Manually Created"),
    ("MANUALLY_UPLOADED", "Manually Uploaded"),
)

TRANSLATION_TYPE_CHOICES = (
    ("MACHINE_GENERATED", "Machine Generated"),
    ("MANUALLY_CREATED", "Manually Created"),
    ("ORIGINAL_SOURCE", "Original Source"),
)

VOICEOVER_TYPE_CHOICES = (
    ("MACHINE_GENERATED", "Machine Generated"),
    ("MANUALLY_CREATED", "Manually Created"),
)

TASK_TYPE = (
    ("TRANSCRIPTION_EDIT", "Transcription Edit"),
    ("TRANSCRIPTION_REVIEW", "Transcription Review"),
    ("TRANSLATION_EDIT", "Translation Edit"),
    ("TRANSLATION_REVIEW", "Translation Review"),
    ("VOICEOVER_EDIT", "VoiceOver Edit"),
)

PRIORITY = (
    ("P1", "Priority No 1"),
    ("P2", "Priority No 2"),
    ("P3", "Priority No 3"),
    ("P4", "Priority No 4"),
)


class Project(models.Model):
    """
    Model for Project Management
    """

    title = models.CharField(max_length=150, help_text=("Project Title"))

    description = models.TextField(
        max_length=1000, null=True, blank=True, help_text=("Project Description")
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name="projects_created",
        verbose_name="created_by",
        help_text=("Project Created By"),
    )

    organization_id = models.ForeignKey(
        Organization,
        on_delete=models.SET_NULL,
        null=True,
        help_text=("Organization to which the Project belongs"),
    )

    managers = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name="projects_managed",
        help_text=("Project Managers"),
    )

    members = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name="projects",
        help_text=("Project Members"),
    )

    is_archived = models.BooleanField(
        verbose_name="project_is_archived",
        default=False,
        help_text=("Indicates whether a project is archived or not."),
    )

    created_at = models.DateTimeField(
        auto_now_add=True, help_text=("Project Created At")
    )

    default_transcript_editor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Project Default Transcript Editor",
        related_name="project_default_transcript_editor",
        on_delete=models.SET_NULL,
        default=None,
        null=True,
        blank=True,
    )

    default_transcript_reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Project Default Transcript Reviewer",
        related_name="project_default_transcript_reviewer",
        on_delete=models.SET_NULL,
        default=None,
        null=True,
        blank=True,
    )

    default_translation_editor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Project Default Translation Editor",
        related_name="project_default_translation_editor",
        on_delete=models.SET_NULL,
        default=None,
        null=True,
        blank=True,
    )

    default_translation_reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Project Default Translation Reviewer",
        related_name="project_default_translation_reviewer",
        on_delete=models.SET_NULL,
        default=None,
        null=True,
        blank=True,
    )

    default_transcript_type = models.CharField(
        choices=TRANSCRIPT_TYPE,
        max_length=35,
        default=None,
        verbose_name="Project Default Transcript Type",
        null=True,
        blank=True,
    )
    default_translation_type = models.CharField(
        choices=TRANSLATION_TYPE_CHOICES,
        max_length=35,
        verbose_name="Project Default Translation Type",
        default=None,
        null=True,
        blank=True,
    )
    default_voiceover_type = models.CharField(
        choices=VOICEOVER_TYPE_CHOICES,
        max_length=35,
        default=None,
        verbose_name="Project Default VoiceOver Type",
        null=True,
        blank=True,
    )
    default_task_types = ArrayField(
        models.CharField(
            choices=TASK_TYPE,
            blank=True,
            default=None,
            null=True,
            max_length=50,
        ),
        blank=True,
        default=None,
        null=True,
    )

    default_target_languages = ArrayField(
        models.CharField(
            choices=TRANSLATION_LANGUAGE_CHOICES,
            blank=True,
            default=None,
            null=True,
            max_length=50,
        ),
        blank=True,
        default=None,
        null=True,
    )

    default_description = models.TextField(
        max_length=400,
        null=True,
        blank=True,
        help_text=("Default Task Description in this Project"),
    )
    default_eta = models.DateTimeField(
        verbose_name="Default_ETA", default=None, blank=True, null=True
    )
    default_priority = models.CharField(
        choices=PRIORITY,
        verbose_name="Default_Priority",
        max_length=2,
        blank=True,
        null=True,
    )
    video_integration = models.BooleanField(
        verbose_name="require_video_integration",
        default=False,
        help_text=(
            "Indicates whether video integration is needed for VO tasks or not."
        ),
    )

    def __str__(self):
        return str(self.title)
