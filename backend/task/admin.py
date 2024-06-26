from django.contrib import admin
from .models import Task


class TaskAdmin(admin.ModelAdmin):
    """
    TaskAdmin class to render the task admin panel.
    """

    list_display = (
        "id",
        "task_type",
        "target_language",
        "video",
        "user",
        "is_active",
        "status",
    )
    search_fields = ("task_type", "status", "is_active")


admin.site.register(Task, TaskAdmin)
