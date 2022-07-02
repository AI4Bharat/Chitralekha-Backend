from django.urls import path, include
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()

router.register(r'', views.TranscriptViewSet)

# Create the url patterns 
urlpatterns = [
    path('generate/', views.create_transcription, name="create_transcription"),
    path('api/', include(router.urls))
]
