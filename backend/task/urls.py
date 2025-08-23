from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework import routers
from . import views

router = routers.DefaultRouter()

router.register(r'api', views.TaskViewSet, basename='task')
# This creates: /task/api/{id}/update_time_spent/

router.register(r'', views.TaskViewSet, basename='task') 
# This creates: /task/{id}/update_time_spent/

urlpatterns = [
    path("", include(router.urls)),
    path("<pk>/import_subtitles", views.import_subtitles, name="import_subtitles"),
]
