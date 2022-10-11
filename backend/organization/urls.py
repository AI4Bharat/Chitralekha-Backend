from rest_framework import routers

from .views import OrganizationViewSet

router = routers.DefaultRouter()

router.register(r"", OrganizationViewSet, basename="organization")

urlpatterns = router.urls
