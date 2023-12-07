from django.db import models
import uuid
from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django import forms
from users.models import User


NEWSLETTER_CATEGORY = (("NEW_FEATURE", "New Feature"),)


class Newsletter(models.Model):
    """
    Model for the Newsletter object.
    """

    newsletter_uuid = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
        verbose_name="Newsletter UUID",
        primary_key=False,
    )
    submitter_id = models.ForeignKey(
        User,
        verbose_name="Submitter User",
        on_delete=models.CASCADE,
    )
    content = models.TextField(help_text=("Newsletter Content"))
    category = models.CharField(
        choices=NEWSLETTER_CATEGORY,
        max_length=35,
        default=None,
        verbose_name="Category of newsletter",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(
        auto_now_add=True, verbose_name="Newsletter Created At"
    )

    def __str__(self):
        return str(self.newsletter_uuid)


class SubscribedUsers(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        related_name="subscribed_user",
        on_delete=models.CASCADE,
        null=False,
        blank=False,
    )
    subscribed_categories = forms.MultipleChoiceField()
    email = models.EmailField(verbose_name="email_address", unique=True, blank=True)

    def __str__(self):
        return str(self.user.email)
