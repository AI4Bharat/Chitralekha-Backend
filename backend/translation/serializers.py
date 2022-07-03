from rest_framework import serializers

from .models import Translation


class TranslationSerializer(serializers.ModelSerializer):
    translation_type = serializers.SerializerMethodField()
    target_lang = serializers.SerializerMethodField()

    def get_translation_type(self, obj):
        return obj.get_translation_type_display()

    def get_target_lang(self, obj):
        return obj.get_target_lang_display()

    class Meta:
        model = Translation
        fields = "__all__"
