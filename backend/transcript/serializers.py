from rest_framework import serializers
from .models import Transcript


class TranscriptTypeSerializer(serializers.Serializer):
    transcript_type = serializers.ListField(child=serializers.CharField())


class TranscriptSerializer(serializers.ModelSerializer):
    class Meta:
        model = Transcript
        fields = "__all__"
