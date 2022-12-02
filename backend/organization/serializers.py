from rest_framework import serializers
from .models import Organization


class OrganizationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = [
            "id",
            "title",
            "email_domain_name",
            "created_by",
            "created_at",
            "organization_owner",
        ]
        read_only_fields = ["id", "created_by", "created_at"]


class InviteGenerationSerializer(serializers.Serializer):
    emails = serializers.ListField(child=serializers.EmailField())
    organization_id = serializers.IntegerField()
    role = serializers.IntegerField()
