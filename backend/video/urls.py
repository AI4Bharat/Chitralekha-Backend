from django.urls import path, include
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()

router.register(r'', views.VideoViewSet)

urlpatterns = [
    path('', views.get_video, name="get_video"),
    path('api', include(router.urls))
]
