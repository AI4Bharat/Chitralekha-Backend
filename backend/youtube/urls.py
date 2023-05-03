from django.urls import path, include
from rest_framework.routers import DefaultRouter

from . import views

urlpatterns = [
    path("revoke_access_token", views.revoke_access_token, name="revoke_access_token"),
    path("store_access_token", views.store_access_token, name="store_access_token"),
    path("upload_to_youtube", views.upload_to_youtube, name="upload_to_youtube"),
]
