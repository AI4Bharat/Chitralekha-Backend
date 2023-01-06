from django.db import models
from django.conf import settings
from django.db import models, transaction
from django.core.mail import send_mail
import secrets
import string
from translation.metadata import LANGUAGE_CHOICES
from django.contrib.postgres.fields import ArrayField

TRANSCRIPT_TYPE = (
    ("ORIGINAL_SOURCE", "Original Source"),
    ("MACHINE_GENERATED", "Machine Generated"),
    ("MANUALLY_CREATED", "Manually Created"),
)

TRANSLATION_TYPE_CHOICES = (
    ("MACHINE_GENERATED", "Machine Generated"),
    ("MANUALLY_CREATED", "Manually Created"),
)

TASK_TYPE = (
    ("TRANSCRIPTION_EDIT", "Transcription Edit"),
    ("TRANSCRIPTION_REVIEW", "Transcription Review"),
    ("TRANSLATION_EDIT", "Translation Edit"),
    ("TRANSLATION_REVIEW", "Translation Review"),
)


class Organization(models.Model):
    """
    Model for organizations
    """

    title = models.CharField(
        verbose_name="organization_title", max_length=512, null=False
    )

    email_domain_name = models.CharField(
        verbose_name="organization_email_domain", max_length=512, null=True
    )

    is_active = models.BooleanField(
        verbose_name="organization_is_active",
        default=True,
        help_text=("Designates whether an organization is active or not."),
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="organization_created",
        verbose_name="created_by",
    )

    organization_owner = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="organization_owned",
        verbose_name="organization_owner",
    )

    default_transcript_editor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="transcript editor",
        related_name="transcript_editor",
        on_delete=models.SET_NULL,
        default=None,
        null=True,
        blank=True,
    )

    default_transcript_reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="transcript reviewer",
        related_name="transcript_reviewer",
        on_delete=models.SET_NULL,
        default=None,
        null=True,
        blank=True,
    )

    default_translation_editor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="translation editor",
        related_name="translation_editor",
        on_delete=models.SET_NULL,
        default=None,
        null=True,
        blank=True,
    )

    default_translation_reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="translation reviewer",
        related_name="translation_reviewer",
        on_delete=models.SET_NULL,
        default=None,
        null=True,
        blank=True,
    )

    default_transcript_type = models.CharField(
        choices=TRANSCRIPT_TYPE,
        max_length=35,
        default=None,
        verbose_name="default transcript type",
        null=True,
        blank=True,
    )

    default_translation_type = models.CharField(
        choices=TRANSLATION_TYPE_CHOICES,
        max_length=35,
        verbose_name="Default Translation Type",
        default=None,
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(verbose_name="created_at", auto_now_add=True)
    updated_at = models.DateTimeField(verbose_name="updated_at", auto_now=True)

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
        verbose_name="Project Default Task Types",
    )

    default_target_languages = ArrayField(
        models.CharField(
            choices=LANGUAGE_CHOICES,
            blank=True,
            default=None,
            null=True,
            max_length=50,
        ),
        blank=True,
        default=None,
        null=True,
        verbose_name="Project Default Target Languages",
    )

    def __str__(self):
        return self.title + ", id=" + str(self.pk)


class Invite(models.Model):
    """
    Invites to invite users to organizations.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        related_name="invite_users",
        on_delete=models.CASCADE,
        null=True,
    )

    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        null=True,
        related_name="invite_oganization",
        verbose_name="organization",
    )

    invite_code = models.CharField(
        verbose_name="invite_code", max_length=256, null=True, unique=True
    )

    def __str__(self):
        return str(self.user.email)

    @classmethod
    def create_invite(cls, organization=None, users=None):
        with transaction.atomic():
            for user in users:
                try:
                    invite = Invite.objects.get(user=user)
                except:
                    invite = Invite.objects.create(organization=organization, user=user)
                    invite.invite_code = cls.generate_invite_code()
                    invite.save()
                if organization is not None:
                    organization_name = organization.title
                else:
                    organization_name = "be the Org Owner."
                send_mail(
                    "Invitation to join Organization",
                    f"Hello! You are invited to {organization_name}. Your Invite link is: https://chitralekha.ai4bharat.org/#/invite/{invite.invite_code}",
                    settings.DEFAULT_FROM_EMAIL,
                    [user.email],
                )

    # def has_permission(self, user):
    #     if self.organization.created_by.pk == user.pk or user.is_superuser:
    #         return True
    #     return False

    @classmethod
    def generate_invite_code(cls):
        return "".join(
            secrets.choice(string.ascii_uppercase + string.digits) for i in range(10)
        )
