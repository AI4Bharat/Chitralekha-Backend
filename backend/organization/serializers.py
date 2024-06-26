from rest_framework import serializers
from .models import Organization, OnboardOrganisationAccount
from users.models import User


class OrgUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "role",
            "has_accepted_invite",
        ]
        read_only_fields = [
            "id",
            "email",
            "role",
            "has_accepted_invite",
        ]


class OrganizationSerializer(serializers.ModelSerializer):
    created_by = OrgUserSerializer(read_only=True)
    organization_owner = OrgUserSerializer(read_only=True)

    class Meta:
        model = Organization
        fields = [
            "id",
            "title",
            "email_domain_name",
            "created_by",
            "created_at",
            "organization_owner",
            "default_task_types",
            "default_target_languages",
            "default_transcript_type",
            "default_translation_type",
            "default_voiceover_type",
            "enable_upload",
        ]
        read_only_fields = ["id", "created_by", "created_at"]


class InviteGenerationSerializer(serializers.Serializer):
    emails = serializers.ListField(child=serializers.EmailField())
    organization_id = serializers.IntegerField()
    role = serializers.IntegerField()


PENDING = "PENDING"
ON_HOLD = "ON_HOLD"
APPROVED = "APPROVED"
REJECTED = "REJECTED"

STATUS_OPTIONS = (
    (PENDING, "Pending"),
    (ON_HOLD, "On Hold"),
    (APPROVED, "Approved"),
    (REJECTED, "Rejected"),
)


class OnboardingOrgAccountSerializer(serializers.ModelSerializer):
    orgname = serializers.CharField()
    org_portal = serializers.CharField()
    email_domain_name = serializers.CharField()
    email = serializers.EmailField()
    org_type = serializers.CharField()
    phone = serializers.CharField()
    interested_in = serializers.CharField()
    src_language = serializers.CharField()
    tgt_language = serializers.CharField()
    status = serializers.ChoiceField(choices=STATUS_OPTIONS)
    purpose = serializers.CharField()
    source = serializers.CharField()
    notes = serializers.CharField()

    class Meta:
        model = OnboardOrganisationAccount
        fields = [
            "id",
            "orgname",
            "org_portal",
            "email_domain_name",
            "email",
            "org_type",
            "phone",
            "status",
            "interested_in",
            "src_language",
            "tgt_language",
            "purpose",
            "source",
            "notes",
        ]
