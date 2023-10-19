from django.contrib import admin

from .models import Newsletter, SubscribedUsers


# Show particular fields in the admin panel
class NewsletterAdmin(admin.ModelAdmin):
    """
    YoutubeAdmin class to render the youtube admin panel.
    """

    list_display = ("newsletter_uuid", "submitter_id", "content", "category")


class SubscribedUsersAdmin(admin.ModelAdmin):
    """
    YoutubeAdmin class to render the youtube admin panel.
    """

    list_display = ("user", "subscribed_categories")


admin.site.register(Newsletter, NewsletterAdmin)
admin.site.register(SubscribedUsers, SubscribedUsersAdmin)
