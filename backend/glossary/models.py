from django.db import models
from django.contrib.postgres.fields import ArrayField
from django.contrib.auth.base_user import AbstractBaseUser
from django.contrib.auth.models import PermissionsMixin
from django.utils import timezone
from django.contrib.postgres.fields import ArrayField
from translation.metadata import TRANSLATION_LANGUAGE_CHOICES
from users.models import User
from organization.models import Organization


class Glossary(models.Model):
    source_language = models.CharField(
        choices=TRANSLATION_LANGUAGE_CHOICES,
        max_length=4,
        verbose_name="Source Language",
        blank=True,
    )
    target_language = models.CharField(
        choices=TRANSLATION_LANGUAGE_CHOICES,
        max_length=4,
        verbose_name="Target Language",
        blank=True,
    )
    source_text = models.CharField(verbose_name="Source Text", max_length=512)
    target_text = models.CharField(verbose_name="Target Text", max_length=512)
    user_id = models.ForeignKey(
        User,
        verbose_name="Created by",
        on_delete=models.CASCADE,
    )
    org_id = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        null=True,
        verbose_name="Glossary at org level",
    )

    def __str__(self):
        return str(self.pk)
