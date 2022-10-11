from rest_framework import serializers
from .models import Project
from users.serializers import UserSerializer

class ProjectSerializer(serializers.ModelSerializer):

    created_by = UserSerializer(read_only=True)
    manager = UserSerializer(read_only=True)
    members = UserSerializer(read_only=True, many=True)

    class Meta:
        model = Project
        fields = ["id", "title", "is_archived", "description", "organization_id", "manager", "members", "created_by", "created_at"]

