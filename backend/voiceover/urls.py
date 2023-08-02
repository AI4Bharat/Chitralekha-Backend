from django.urls import path
from . import views


urlpatterns = [
    path("save/", views.save_voice_over, name="save_voice_over"),
    path(
        "get_voiceover_supported_languages",
        views.get_voiceover_supported_languages,
        name="get_voiceover_supported_languages",
    ),
    path(
        "get_voice_over_types/",
        views.get_voice_over_types,
        name="get_voice_over_types",
    ),
    path(
        "get_empty_audios/",
        views.get_empty_audios,
        name="get_empty_audios",
    ),
    path(
        "get_payload/",
        views.get_payload,
        name="get_payload",
    ),
    path("export_voiceover/", views.export_voiceover, name="export_voiceover/"),
    path(
        "get_voice_over_task_counts/",
        views.get_voice_over_task_counts,
        name="get_voice_over_task_counts/",
    ),
    path(
        "get_voice_over_export_types/",
        views.get_voice_over_export_types,
        name="get_voice_over_export_types",
    ),
    path(
        "get_report_voiceover/",
        views.get_voiceover_report,
        name="get_voiceover_report",
    ),
]
