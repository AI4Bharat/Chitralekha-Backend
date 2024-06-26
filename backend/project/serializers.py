from rest_framework import serializers
from .models import Project
from users.serializers import UserFetchSerializer


class ProjectSerializer(serializers.ModelSerializer):
    created_by = UserFetchSerializer(read_only=True)
    managers = UserFetchSerializer(read_only=True, many=True)
    members = UserFetchSerializer(read_only=True, many=True)

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
            "default_task_types",
            "default_target_languages",
            "default_transcript_type",
            "default_translation_type",
            "default_voiceover_type",
            "default_eta",
            "default_priority",
            "default_description",
            "video_integration",
            "pre_generate_audio"
        ]
