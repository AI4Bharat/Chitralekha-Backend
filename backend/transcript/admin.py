from django.contrib import admin

from .models import Transcript


# Show particular fields in the admin panel 
class TranscriptAdmin(admin.ModelAdmin):
    list_display = ('id', 'video', 'language', 'transcript_type', 'payload') 
    list_filter = ('video', 'language', 'transcript_type')
    search_fields = ('video', 'language', 'transcript_type')
    ordering = ('id',)

# Register the model in the admin panel
admin.site.register(Transcript, TranscriptAdmin)

