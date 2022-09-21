from django.contrib import admin

from .models import Translation

# Show particular fields in the admin panel
class TranslationAdmin(admin.ModelAdmin):
    """
    TranslationAdmin class to render the translation admin panel.
    """

    list_display = ("id", "transcript", "target_language", "translation_type", "updated_at")
    list_filter = ("transcript", "target_language", "translation_type")
    search_fields = ("transcript", "target_language", "translation_type")
    ordering = ("-updated_at",)


admin.site.register(Translation, TranslationAdmin)
