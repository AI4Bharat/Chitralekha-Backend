from django.db import models
from django.contrib.postgres.fields import ArrayField
from django.contrib.auth.base_user import AbstractBaseUser
from django.contrib.auth.models import PermissionsMixin
from django.utils import timezone
from django.contrib.postgres.fields import ArrayField
from translation.metadata import TRANSLATION_LANGUAGE_CHOICES
from users.models import User
from organization.models import Organization
from task.models import Task
from .metadata import DOMAIN

DOMAIN_CHOICES = [(domain["code"], domain["label"]) for domain in DOMAIN["domains"]]


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
    text_meaning = models.CharField(verbose_name="Text Meaning", max_length=512, null=True, blank=True)
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
    task_ids = models.ManyToManyField(Task)
    context = models.CharField(
        choices=DOMAIN_CHOICES,
        default="general",
        max_length=50,
        verbose_name="Context",
    )

    def __str__(self):
        return str(self.pk)
