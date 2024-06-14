from django.urls import path

from . import views


urlpatterns = [
    path("", views.retrieve_translation, name="retrieve_translation"),
    path("save/", views.save_translation, name="save_translation"),
    path(
        "get_translation_supported_languages",
        views.get_translation_supported_languages,
        name="get_translation_supported_languages",
    ),
    path("get_speaker_info", views.get_speaker_info, name="get_speaker_info"),
    path("update_speaker_info", views.update_speaker_info, name="update_speaker_info"),
    path("generate", views.generate_translation, name="generate_translation"),
    path(
        "generate_translation_output/",
        views.generate_translation_output,
        name="generate_translation_output",
    ),
    path(
        "get_translation_types/",
        views.get_translation_types,
        name="get_translation_types",
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
    path(
        "get_full_payload/",
        views.get_full_payload,
        name="get_full_payload",
    ),
    path(
        "get_translation_export_types/",
        views.get_translation_export_types,
        name="get_translation_export_types",
    ),
    path(
        "export_translation/",
        views.export_translation,
        name="export_translation",
    ),
    path(
        "get_report_translation/",
        views.get_translation_report,
        name="get_translation_report",
    ),
    path(
        "get_sentence_from_timeline/",
        views.get_sentence_from_timeline,
        name="get_sentence_from_timeline",
    ),
]
