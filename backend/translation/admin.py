from django.contrib import admin

from .models import Translation


# Show particular fields in the admin panel
class TranslationAdmin(admin.ModelAdmin):
    """
    TranslationAdmin class to render the translation admin panel.
    """

    list_display = (
        "task",
        "transcript",
        "target_language",
        "id",
        "translation_type",
        "updated_at",
        "id",
        "status",
    )
    list_filter = ("task", "transcript", "target_language", "translation_type")
    search_fields = ("task", "transcript", "target_language", "translation_type")
    ordering = ("-updated_at",)


admin.site.register(Translation, TranslationAdmin)
