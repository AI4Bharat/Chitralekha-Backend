from django.urls import path
from . import views


urlpatterns = [
    path("reopen_translation_voiceover_task/", views.reopen_translation_voiceover_task, name = "reopen_translation_voiceover_task"),
    path("get_translated_text/", views.get_translated_text, name = "get_translated_text"),
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
        "update_completed_count/",
        views.update_completed_count,
        name="update_completed_count",
    ),
    path(
        "get_payload/",
        views.get_payload,
        name="get_payload",
    ),
    path(
        "replace_all_words/",
        views.replace_all_words,
        name="replace_all_words",
    ),
    path("export_voiceover/", views.export_voiceover, name="export_voiceover/"),
    path(
        "bulk_export_voiceover/",
        views.bulk_export_voiceover,
        name="bulk_export_voiceover/",
    ),
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
