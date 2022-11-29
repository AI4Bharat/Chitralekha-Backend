from rest_framework.serializers import ModelSerializer
from rest_framework import serializers
from .models import Task
from video.models import Video


class TaskSerializer(ModelSerializer):
    video_name = serializers.CharField(source="video.name", read_only=True)
    src_language = serializers.CharField(source="video.language", read_only=True)

    class Meta:
        model = Task
        fields = (
            "id",
            "task_type",
            "video",
            "video_name",
            "src_language",
            "target_language",
            "status",
            "user",
            "eta",
            "priority",
            "description",
        )
