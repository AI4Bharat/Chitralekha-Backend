from rest_framework import serializers
from .models import Organization
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
