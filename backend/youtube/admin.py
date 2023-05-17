from django.contrib import admin

from .models import Youtube


# Show particular fields in the admin panel
class YoutubeAdmin(admin.ModelAdmin):
    """
    YoutubeAdmin class to render the youtube admin panel.
    """

    list_display = ("youtube_uuid", "channel_id", "project_id")


admin.site.register(Youtube, YoutubeAdmin)
