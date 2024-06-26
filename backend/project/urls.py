from rest_framework import routers

from .views import ProjectViewSet

router = routers.DefaultRouter()

router.register(r"", ProjectViewSet, basename="project")

urlpatterns = router.urls
