from rest_framework import serializers
from .models import Task, TASK_TYPE
from video.models import Video


class TaskSerializer(serializers.ModelSerializer):
    video_name = serializers.CharField(source="video.name", read_only=True)
    src_language = serializers.CharField(source="video.language", read_only=True)
    video_url = serializers.CharField(source="video.url", read_only=True)
    project = serializers.CharField(source="video.project_id.id", read_only=True)
    user_email = serializers.CharField(source="user.email", read_only=True)

    class Meta:
        model = Task
        fields = (
            "id",
            "task_type",
            "video",
            "video_name",
            "src_language",
            "video_url",
            "project",
            "target_language",
            "status",
            "user",
            "user_email",
            "eta",
            "priority",
            "description",
            "created_at",
            "updated_at",
        )
