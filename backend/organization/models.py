from django.db import models
from django.contrib.auth.models import User

class Organization(models.Model):
    """
    Model for organizations
    """

    title = models.CharField(
        verbose_name='organization_title', max_length=512, null=False
    )

    email_domain_name = models.CharField(
        verbose_name="organization_email_domain", max_length=512, null=True
    )

    is_active = models.BooleanField(
        verbose_name="organization_is_active",
        default=True,
        help_text=("Designates whether an organization is active or not."),
    )

    created_by = models.OneToOneField(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="organization_created",
        verbose_name="created_by",
    )

    organization_owner = models.OneToOneField(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="organization_owned",
        verbose_name="organization_owner",
    )

    created_at = models.DateTimeField(verbose_name="created_at", auto_now_add=True)
    updated_at = models.DateTimeField(verbose_name="updated_at", auto_now=True)

    def __str__(self):
        return self.title + ", id=" + str(self.pk)
