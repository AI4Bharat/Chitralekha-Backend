from django.urls import path

from . import views


urlpatterns = [
    path("", views.retrieve_translation, name="retrieve_translation"),
    path("save", views.save_translation, name="save_translation"),
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
]
