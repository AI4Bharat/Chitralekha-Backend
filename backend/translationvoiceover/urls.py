from django.urls import path
from . import views


urlpatterns = [
    path(
        "get_voice_over_export_types/",
        views.get_voice_over_export_types,
        name="get_voice_over_export_types",
    ),
    path(
        "get_translation_export_types/",
        views.get_translation_export_types,
        name="get_translation_export_types",
    ),
   
]