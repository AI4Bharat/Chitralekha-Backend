from django.urls import path

from . import views


urlpatterns = [
    path("", views.retrieve_translation, name="retrieve_translation"),
    path("save/", views.save_translation, name="save_translation"),
    path(
        "generate/supported_languages",
        views.get_supported_languages,
        name="supported_languages",
    ),
    path("generate", views.generate_translation, name="generate_translation"),
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
]
