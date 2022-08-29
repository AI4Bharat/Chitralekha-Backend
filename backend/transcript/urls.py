from django.urls import path, include
from rest_framework.routers import DefaultRouter

from . import views

# Create the url patterns
urlpatterns = [
    path("generate/", views.create_transcription, name="create_transcription"),
    path(
        "generate_from_youtube/",
        views.create_youtube_transcription,
        name="create_transcription_from_youtube",
    ),
    path("save/", views.save_transcription, name="save_transcript"),
    path("", views.retrieve_transcription, name="retrieve_transcription"),
    path(
        "generate/supported_languages",
        views.get_supported_languages,
        name="get_supported_languages",
    ),
]
