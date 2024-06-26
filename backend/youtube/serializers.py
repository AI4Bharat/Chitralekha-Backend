from rest_framework import serializers
from .models import Youtube


class YoutubeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Youtube
        fields = (
            "id",
            "youtube_uuid",
            "channel_id",
            "project_id",
        )
