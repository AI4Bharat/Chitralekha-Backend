from django.db import models
from django.conf import settings
from django.db import models, transaction
from django.core.mail import EmailMultiAlternatives
import secrets
import string
from translation.metadata import TRANSLATION_LANGUAGE_CHOICES
from django.contrib.postgres.fields import ArrayField
from config import frontend_url
import os
from utils.email_template import invite_email_template

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


class Organization(models.Model):
    """
    Model for organizations
    """

    title = models.CharField(
        verbose_name="organization_title", max_length=512, null=False, unique=True
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
        verbose_name="Organization Default Task Types",
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
        verbose_name="Organization Default Target Languages",
    )
    description = models.TextField(
        max_length=1000, null=True, blank=True, help_text=("Organization Description")
    )
    enable_upload = models.BooleanField(
        verbose_name="enable_upload",
        default=False,
        help_text=("Indicates whether CSV upload is enable or not."),
    )

    def __str__(self):
        return self.title + ", id=" + str(self.pk)

PENDING="PENDING"
ON_HOLD="ON_HOLD"
APPROVED="APPROVED"
REJECTED="REJECTED"

STATUS_OPTIONS = (
    (PENDING, "Pending"),
    (ON_HOLD, "On Hold"),
    (APPROVED, "Approved"),
    (REJECTED, "Rejected"),
)
class OnboardOrganisationAccount(models.Model):
    """
    Onboard Organisation Requests.
    """
    orgname = models.CharField(verbose_name="orgname", max_length=512, null=False, help_text=("Title of Organization"))
    org_portal = models.CharField(verbose_name="org_portal", max_length=512, help_text=("Organization website portal"))
    email_domain_name = models.CharField(verbose_name="organization_email_domain", max_length=512, null=True, blank=True, help_text=("Organization email domain"))
    email = models.EmailField(verbose_name="email_address", unique=True, blank=False, help_text=("Organization owner email address"))
    org_type = models.CharField(verbose_name="org_type", max_length=512)
    phone = models.CharField(
        verbose_name="phone", max_length=256, null=True, blank=True
    )
    status = models.CharField(
        choices=STATUS_OPTIONS,
        max_length=35,
        default=PENDING,
        verbose_name="Onboarding Status",
        help_text=("Current status of organization onboard request")
    )
    
    interested_in = models.CharField(verbose_name="interested_in", max_length=512, help_text=("Interested in Translation, Transcription, VoiceOver"))
    src_language = models.CharField(verbose_name="src_language", max_length=512, null=True, blank=True,)
    tgt_language = models.CharField(verbose_name="tgt_language", max_length=512, null=True, blank=True,)
    purpose = models.TextField(max_length=2000, null=True, blank=True, help_text=("Purpose for using Chitralekha"))
    source = models.TextField(max_length=2000, null=True, blank=True, help_text=("Source from where user came to know about Chitralekha"))
    # notes = models.TextField(max_length=1000, null=True, blank=True, help_text=("Notes for updating status"))
    notes = ArrayField(
        models.CharField(
            max_length=1000,
            blank=True
        ),
        blank=True,
        default=None,
        null=True,
        help_text=("Notes provided while updating the status of the onboarding request")
    )

    def __str__(self):
        return str(self.email)


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
    def send_invite_email(cls, invite, user):
        current_environment = os.getenv("ENV")
        base_url = (
            "dev.chitralekha.ai4bharat.org"
            if current_environment == "dev"
            else "chitralekha.ai4bharat.org"
        )
        subject = "Invitation to join Chitralekha Organization"
        invite_link = f"https://{base_url}/#/invite/{invite.invite_code}"
        message = "Please use the above link to verify your email address and complete your registration."
        
        try :
            compiled_msg_code = invite_email_template(
                subject=subject,invite_link=invite_link,message=message
            )
            msg = EmailMultiAlternatives(
                subject,
                compiled_msg_code,
                settings.DEFAULT_FROM_EMAIL,
                [user.email],
            )
            msg.attach_alternative(compiled_msg_code, "text/html")
            msg.send()

        except Exception as e:
            print(f"Failed to send email: {str(e)}")
            raise e

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
                cls.send_invite_email(invite, user)
                # send_mail(
                #     "Invitation to join Organization",
                #     f"Hello! You are invited to {organization_name}. Your Invite link is: {frontend_url}/#/invite/{invite.invite_code}",
                #     settings.DEFAULT_FROM_EMAIL,
                #     [user.email],
                # )

    @classmethod
    def re_invite(cls, users=None):
        with transaction.atomic():
            for user in users:
                invite = Invite.objects.get(user=user)
                cls.send_invite_email(invite, user)
    # def has_permission(self, user):
    #     if self.organization.created_by.pk == user.pk or user.is_superuser:
    #         return True
    #     return False

    @classmethod
    def generate_invite_code(cls):
        return "".join(
            secrets.choice(string.ascii_uppercase + string.digits) for i in range(10)
        )
