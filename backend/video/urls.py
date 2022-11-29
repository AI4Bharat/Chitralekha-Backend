from django.urls import path, include
from rest_framework.routers import DefaultRouter

from . import views

urlpatterns = [
    path("", views.get_video, name="get_video"),
    path("list_recent", views.list_recent, name="list_recent"),
    path("list_tasks", views.list_tasks, name="list_tasks"),
]
