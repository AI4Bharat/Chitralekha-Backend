from django.contrib import admin

from .models import Transcript


# Show particular fields in the admin panel
class TranscriptAdmin(admin.ModelAdmin):
    list_display = ("task", "video", "language", "transcript_type", "updated_at", "id")
    list_filter = ("video", "language", "transcript_type")
    search_fields = ("video", "language", "transcript_type")
    ordering = ("-updated_at",)


# Register the model in the admin panel
admin.site.register(Transcript, TranscriptAdmin)
