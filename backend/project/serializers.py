from rest_framework import serializers
from .models import Project
from users.serializers import UserProfileSerializer


class ProjectSerializer(serializers.ModelSerializer):

    created_by = UserProfileSerializer(read_only=True)
    managers = UserProfileSerializer(read_only=True, many=True)
    members = UserProfileSerializer(read_only=True, many=True)

    class Meta:
        model = Project
        fields = [
            "id",
            "title",
            "is_archived",
            "description",
            "organization_id",
            "managers",
            "members",
            "created_by",
            "created_at",
        ]
