from rest_framework import serializers
from .models import Task, TASK_TYPE
from video.models import Video
from translation.metadata import LANGUAGE_CHOICES
from users.serializers import UserFetchSerializer
from project.serializers import ProjectSerializer


class TaskStatusSerializer(serializers.ModelSerializer):
    language_pair = serializers.CharField(source="get_language_pair_label")
    task_status = serializers.CharField(source="get_task_status")
    user = UserFetchSerializer(read_only=True)

    class Meta:
        model = Task
        fields = ("language_pair", "task_status", "user", "created_at")


class TaskSerializer(serializers.ModelSerializer):
    video_name = serializers.CharField(source="video.name", read_only=True)
    src_language = serializers.CharField(source="video.language", read_only=True)
    video_url = serializers.CharField(source="video.url", read_only=True)
    is_audio_only = serializers.BooleanField(source="video.audio_only", read_only=True)
    project = serializers.CharField(source="video.project_id.id", read_only=True)
    project_name = serializers.CharField(source="video.project_id", read_only=True)
    src_language_label = serializers.CharField(source="get_src_language_label")
    source_type = serializers.CharField(source="get_source_type")
    target_language_label = serializers.CharField(source="get_target_language_label")
    task_type_label = serializers.CharField(source="get_task_type_label")
    status_label = serializers.CharField(source="get_task_status_label")
    user = UserFetchSerializer(read_only=True)
    created_by = UserFetchSerializer(read_only=True)

    class Meta:
        model = Task
        fields = (
            "id",
            "task_type",
            "task_type_label",
            "video",
            "video_name",
            "is_audio_only",
            "src_language",
            "src_language_label",
            "video_url",
            "project",
            "project_name",
            "target_language",
            "target_language_label",
            "source_type",
            "status",
            "status_label",
            "user",
            "eta",
            "priority",
            "description",
            "created_at",
            "updated_at",
            "created_by",
            "is_active",
            "time_spent",
        )
