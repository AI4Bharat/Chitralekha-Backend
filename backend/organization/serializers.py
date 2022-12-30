from rest_framework import serializers
from .models import Organization


class OrganizationSerializer(serializers.ModelSerializer):
    created_by_email = serializers.CharField(source="created_by.email", read_only=True)
    organization_owner_email = serializers.CharField(
        source="organization_owner.email", read_only=True
    )

    class Meta:
        model = Organization
        fields = [
            "id",
            "title",
            "email_domain_name",
            "created_by",
            "created_by_email",
            "created_at",
            "organization_owner",
            "organization_owner_email",
        ]
        read_only_fields = ["id", "created_by", "created_at"]


class InviteGenerationSerializer(serializers.Serializer):
    emails = serializers.ListField(child=serializers.EmailField())
    organization_id = serializers.IntegerField()
    role = serializers.IntegerField()
