from django.urls import path, include
from rest_framework import routers
from .views import UserViewSet, InviteViewSet, LanguageViewSet, RoleViewSet, SoftDeleteUserViewSet
#from .serializers import CustomTokenCreateViewSerialize


app_name = "users"

router = routers.DefaultRouter()

router.register(r"account", UserViewSet, basename="account")
router.register(r"invite", InviteViewSet, basename="invite")
router.register(r"languages", LanguageViewSet, basename="languages")
router.register(r"roles", RoleViewSet, basename="roles")

urlpatterns = [
    path('auth/users/<int:pk>/', SoftDeleteUserViewSet.as_view({'delete': 'destroy'}), name='user-detail'),
    path("auth/", include("djoser.urls")),
    path("auth/", include("djoser.urls.jwt")),
    path("", include(router.urls)),
]
