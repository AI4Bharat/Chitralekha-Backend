from django.contrib import admin

from .models import Video


# Show particular fields in the admin panel
class VideoAdmin(admin.ModelAdmin):
    """
    VideoAdmin class to render the video admin panel.
    """

    list_display = ("id", "name", "url", "duration", "video_uuid")


admin.site.register(Video, VideoAdmin)
