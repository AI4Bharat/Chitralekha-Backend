from django.urls import path

from . import views


urlpatterns = [
    path("save/", views.save_voice_over, name="save_voice_over"),
    path(
        "generate/supported_languages",
        views.get_supported_languages,
        name="supported_languages",
    ),
    path(
        "get_voice_over_types/",
        views.get_voice_over_types,
        name="get_voice_over_types",
    ),
    path(
        "get_payload/",
        views.get_payload,
        name="get_payload",
    ),
]
