from rest_framework import serializers

from .models import Translation


class TranslationSerializer(serializers.ModelSerializer):
    translation_type = serializers.SerializerMethodField()

    def get_translation_type(self, obj):
        return obj.get_translation_type_display()

    class Meta:
        model = Translation
        fields = "__all__"
