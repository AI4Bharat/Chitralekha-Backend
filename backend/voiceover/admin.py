from django.contrib import admin
from .models import VoiceOver


# Show particular fields in the admin panel
class VoiceOverAdmin(admin.ModelAdmin):
    """
    VoiceOverAdmin class to render the voiceover admin panel.
    """

    list_display = (
        "id",
        "translation",
        "video",
        "voice_over_type",
        "updated_at",
    )
    list_filter = ("video", "voice_over_type", "translation")
    search_fields = ("video", "voice_over_type", "translation")
    ordering = ("-updated_at",)


admin.site.register(VoiceOver, VoiceOverAdmin)
