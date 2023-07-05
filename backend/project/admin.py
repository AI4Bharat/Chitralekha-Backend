from django.contrib import admin
from .models import Project


class ProjectAdmin(admin.ModelAdmin):
    """
    TaskAdmin class to render the task admin panel.
    """

    list_display = (
        "id",
        "organization_id",
        "default_task_types",
        "default_target_languages",
    )


admin.site.register(Project, ProjectAdmin)
