from rest_framework import routers
from django.urls import path

from .views import OrganizationViewSet, OnboardingOrgAccountApiView

router = routers.DefaultRouter()

router.register(r"", OrganizationViewSet, basename="organization")

urlpatterns = [
    path( "onboard/", OnboardingOrgAccountApiView.as_view(), name='OnboardingOrgAccountApiView'),
    path( "onboard/<int:pk>/", OnboardingOrgAccountApiView.as_view(), name='OnboardingOrgAccountApiView'),
]

urlpatterns += router.urls
