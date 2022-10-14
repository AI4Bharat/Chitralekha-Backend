from rest_framework import serializers
from .models import Project
from users.serializers import UserProfileSerializer

class ProjectSerializer(serializers.ModelSerializer):

    created_by = UserProfileSerializer(read_only=True)
    manager = UserProfileSerializer(read_only=True)
    members = UserProfileSerializer(read_only=True, many=True)

    class Meta:
        model = Project
        fields = ["id", "title", "is_archived", "description", "organization_id", "manager", "members", "created_by", "created_at"]
