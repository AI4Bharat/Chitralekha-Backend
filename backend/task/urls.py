from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework import routers
from . import views

router = routers.DefaultRouter()

router.register(r"", views.TaskViewSet, basename="task")

urlpatterns = router.urls
