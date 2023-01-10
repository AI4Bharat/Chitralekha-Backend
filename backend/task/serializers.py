from rest_framework import serializers
from .models import Task, TASK_TYPE
from video.models import Video
from translation.metadata import LANGUAGE_CHOICES
from users.serializers import UserFetchSerializer


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
    project = serializers.CharField(source="video.project_id.id", read_only=True)
    src_language_label = serializers.CharField(source="get_src_language_label")
    target_language_label = serializers.CharField(source="get_target_language_label")
    task_type_label = serializers.CharField(source="get_task_type_label")
    user = UserFetchSerializer(read_only=True)

    class Meta:
        model = Task
        fields = (
            "id",
            "task_type",
            "task_type_label",
            "video",
            "video_name",
            "src_language",
            "src_language_label",
            "video_url",
            "project",
            "target_language",
            "target_language_label",
            "status",
            "user",
            "eta",
            "priority",
            "description",
            "created_at",
            "updated_at",
            "is_active",
        )
