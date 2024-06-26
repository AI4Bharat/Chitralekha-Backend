from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework import routers
from . import views

router = routers.DefaultRouter()

router.register(r"", views.NewsletterViewSet, basename="newsletter")

urlpatterns = [
    path("", include(router.urls)),
    path("unsubscribe", views.unsubscribe, name="unsubscribe"),
]
