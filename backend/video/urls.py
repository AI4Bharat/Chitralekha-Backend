from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import TransliterationAPIView
from . import views

urlpatterns = [
    path("", views.get_video, name="get_video"),
    path(
        "xlit-api/generic/transliteration/<str:target_language>/<str:data>",
        TransliterationAPIView.as_view(),
        name="transliteration-api",
    ),
    path("delete_video", views.delete_video, name="delete_video"),
    path("list_recent", views.list_recent, name="list_recent"),
    path("list_tasks", views.list_tasks, name="list_tasks"),
    path("download_all", views.download_all, name="download_all"),
    path("update_video", views.update_video, name="update_video"),
    path("upload_csv", views.upload_csv, name="upload_csv"),
    path("upload_csv_data", views.upload_csv_data, name="upload_csv_data"),
    path("upload_csv_org", views.upload_csv_org, name="upload_csv_org"),
]
