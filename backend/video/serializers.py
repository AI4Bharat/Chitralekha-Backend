from rest_framework import serializers
from .models import Video


class VideoSerializer(serializers.ModelSerializer):
    language_label = serializers.CharField(source="get_language_label")

    class Meta:
        model = Video
        fields = (
            "id",
            "video_uuid",
            "name",
            "url",
            "language",
            "description",
            "duration",
            "subtitles",
            "audio_only",
            "project_id",
            "language_label",
            "gender",
        )
