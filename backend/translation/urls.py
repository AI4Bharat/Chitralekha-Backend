from django.urls import path

from . import views


urlpatterns = [
    path("", views.TranslationView.as_view(), name="translation"),
    path(
        "generate/supported_languages",
        views.get_supported_languages,
        name="supported_languages",
    ),
    path("generate", views.generate_translation, name="generate_translation"),
]
