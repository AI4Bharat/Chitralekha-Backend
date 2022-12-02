from rest_framework import serializers

from .models import Translation


class TranslationTypeSerializer(serializers.Serializer):
    translation_type = serializers.ListField(child=serializers.CharField())


class TranslationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Translation
        fields = "__all__"
