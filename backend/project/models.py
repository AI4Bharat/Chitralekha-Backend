from django.db import models
from django.conf import settings
from organization.models import Organization


TRANSCRIPT_TYPE = (
    ("ORIGINAL_SOURCE", "Original Source"),
    ("MACHINE_GENERATED", "Machine Generated"),
    ("MANUALLY_CREATED", "Manually Created"),
)

TRANSLATION_TYPE_CHOICES = (
    ("MACHINE_GENERATED", "Machine Generated"),
    ("MANUALLY_CREATED", "Manually Created"),
)


class Project(models.Model):
    """
    Model for Project Management
    """

    title = models.CharField(max_length=100, help_text=("Project Title"))

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
    )

    default_transcript_reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Project Default Transcript Reviewer",
        related_name="project_default_transcript_reviewer",
        on_delete=models.SET_NULL,
        default=None,
        null=True,
    )

    default_translation_editor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Project Default Translation Editor",
        related_name="project_default_translation_editor",
        on_delete=models.SET_NULL,
        default=None,
        null=True,
    )

    default_translation_reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Project Default Translation Reviewer",
        related_name="project_default_translation_reviewer",
        on_delete=models.SET_NULL,
        default=None,
        null=True,
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

    def __str__(self):
        return str(self.title)
