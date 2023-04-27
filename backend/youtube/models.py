from django.db import models
import uuid
from project.models import Project
from django.contrib.postgres.fields import ArrayField


class Youtube(models.Model):
    """
    Model for the Youtube object.
    """

    youtube_uuid = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
        verbose_name="Youtube UUID",
        primary_key=False,
    )
    channel_id = models.URLField(verbose_name="Youtube channel", db_index=True)
    project_id = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        help_text=("Youtube to which the Project belongs"),
    )
    auth_token = models.JSONField(verbose_name="Auth token", null=False, blank=False)

    def __str__(self):
        return str(self.youtube_uuid) + " : " + self.name
