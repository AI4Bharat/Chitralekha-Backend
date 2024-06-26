from rest_framework import serializers
from .models import VoiceOver


class VoiceOverSerializer(serializers.ModelSerializer):
    class Meta:
        model = VoiceOver
        fields = "__all__"
