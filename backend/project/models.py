from django.db import models
from django.contrib.auth.models import User
from organization.models import Organization

class Project(models.Model):
    """
    Model for Project Management
    """

    title = models.CharField(max_length=100, help_text=("Project Title"))

    description = models.TextField(
        max_length=1000, null=True, blank=True, help_text=("Project Description")
    )

    created_by = models.ForeignKey(
        User,
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

    manager = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="projects_managed",
        help_text=("Project Manager"),
    )

    members = models.ManyToManyField(
        User,
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

    def __str__(self):
        return str(self.title)


