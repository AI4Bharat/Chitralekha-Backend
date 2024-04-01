"""backend URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.conf import settings
from django.contrib import admin
from django.urls import include, path, re_path
from rest_framework import routers, permissions
from drf_yasg.views import get_schema_view
from drf_yasg import openapi
from drf_yasg.generators import OpenAPISchemaGenerator
from video.views import TransliterationAPIView
from users.views import OnboardingAPIView
from config import app_name

## Utility Classes
class BothHttpAndHttpsSchemaGenerator(OpenAPISchemaGenerator):
    def get_schema(self, request=None, public=False):
        schema = super().get_schema(request, public)
        schema.schemes = ["http", "https"]
        return schema


class HttpsOnlySchemaGenerator(OpenAPISchemaGenerator):
    def get_schema(self, request=None, public=False):
        schema = super().get_schema(request, public)
        schema.schemes = ["https"]
        return schema


router = routers.DefaultRouter()
# Register the viewsets

# Add the swagger view
schema_view = get_schema_view(
    openapi.Info(
        title=app_name + " API Docs",
        default_version="v1",
        description=f"API documentation for {app_name} Platform.",
        terms_of_service="https://www.google.com/policies/terms/",
        contact=openapi.Contact(email="contact@snippets.local"),
        license=openapi.License(name="BSD License"),
    ),
    generator_class=BothHttpAndHttpsSchemaGenerator
    if settings.DEBUG
    else HttpsOnlySchemaGenerator,
    public=True,
    permission_classes=[permissions.AllowAny],
)

urlpatterns = [
    path("", include(router.urls)),
    path("admin/", admin.site.urls),
    path("users/", include("users.urls")),
    path("organization/", include("organization.urls")),
    path("project/", include("project.urls")),
    path("video/", include("video.urls")),
    path("task/", include("task.urls")),
    path("translation/", include("translation.urls")),
    path("transcript/", include("transcript.urls")),
    path("voiceover/", include("voiceover.urls")),
    path("youtube/", include("youtube.urls")),
    path(
        "api/generic/transliteration/<str:target_language>/<str:data>/",
        TransliterationAPIView.as_view(),
        name="transliteration-api",
    ),
    path(
        "onboarding/<str:org_name>/<str:org_portal>/<str:email_id>/<str:phone>/<str:org_type>/<str:purpose>/<str:source>/<str:interested_in>/<str:src_language>/<str:tgt_language>/",
        OnboardingAPIView.as_view(),
        name="onboarding-api",
    ),
    path("newsletter/", include("newsletter.urls")),
    path("glossary/", include("glossary.urls")),
    re_path(
        r"^swagger(?P<format>\.json|\.yaml)$",
        schema_view.without_ui(cache_timeout=0),
        name="schema-json",
    ),
    path(
        "swagger/",
        schema_view.with_ui("swagger", cache_timeout=0),
        name="schema-swagger-ui",
    ),
    re_path(
        r"^redoc/$", schema_view.with_ui("redoc", cache_timeout=0), name="schema-redoc"
    ),
]
