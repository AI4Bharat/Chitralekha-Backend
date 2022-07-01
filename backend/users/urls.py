from django.contrib import admin
from django.urls import include, path
from knox import views as knox_views

from .views import LoginAPI, RegisterAPIView, UserDetailAPI

urlpatterns = [
    path("user/<str:pk>/",UserDetailAPI.as_view()),
    path('api/register/',RegisterAPIView.as_view(), name='register'),
    path('api/login/', LoginAPI.as_view(), name='login'),
    path('api/logout/', knox_views.LogoutView.as_view(), name='logout'),
    path('api/logoutall/', knox_views.LogoutAllView.as_view(), name='logoutall'),
]
