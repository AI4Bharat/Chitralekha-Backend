from django.urls import path, include
from rest_framework import routers
from .views import UserViewSet, InviteViewSet, LanguageViewSet, RoleViewSet, CustomTokenCreateView


app_name = "users"

router = routers.DefaultRouter()

router.register(r"account", UserViewSet, basename="account")
router.register(r"invite", InviteViewSet, basename="invite")
router.register(r"languages", LanguageViewSet, basename="languages")
router.register(r"roles", RoleViewSet, basename="roles")

urlpatterns = [
    # Override the default auth/jwt/create/ URL with the custom view
    path("auth/jwt/create/", CustomTokenCreateView.as_view(), name="jwt-create"),
    path("auth/", include("djoser.urls")),
    # path("auth/", include("djoser.urls.jwt")),
    path("", include(router.urls)),
]
