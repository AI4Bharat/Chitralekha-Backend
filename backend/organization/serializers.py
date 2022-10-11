from rest_framework import serializers
from .models import Organization

class OrganizationSerializer(serializers.ModelSerializer):

    class Meta:
        model = Organization
        fields = ["id", "title", "email_domain_name", "created_by", "created_at"]
        read_only_fields = ["id", "created_by", "created_at"]

