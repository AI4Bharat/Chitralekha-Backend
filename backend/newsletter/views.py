from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet
from rest_framework.decorators import action
from users.models import User
from django.db.models import Count, Q
from rest_framework.permissions import IsAuthenticated
import webvtt
from io import StringIO
import json, sys
from .models import NEWSLETTER_CATEGORY, Newsletter
from .serializers import NewsletterSerializer
from users.models import User
from rest_framework.response import Response
from rest_framework import status
import logging
from django.http import HttpResponse
import requests
from django.http import HttpRequest
from organization.decorators import is_admin


class NewsletterViewSet(ModelViewSet):
    """
    API ViewSet for the Video model.
    Performs CRUD operations on the Video model.
    Endpoint: /video/api/
    Methods: GET, POST, PUT, DELETE
    """

    queryset = Newsletter.objects.all()
    serializer_class = NewsletterSerializer
    permission_classes = (IsAuthenticated,)

    @is_admin
    def create(self, request, pk=None, *args, **kwargs):
        category = request.data.get("category")
        content = request.data.get("content")
        submitter_id = request.data.get("submitter_id")

        if content is None or content == "":
            return Response(
                {"message": "missing param : content can't be empty"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        new_newsletter = Newsletter(
            content=content, submitter_id=submitter_id, category="NEW_FEATURE"
        )
        new_newsletter.save()
        return Response(
            {"message": "Newsletter is successfully submitted."},
            status=status.HTTP_200_OK,
        )

    @swagger_auto_schema(
        method="post",
        manual_parameters=[
            openapi.Parameter(
                "email",
                openapi.IN_QUERY,
                description=("Email Id of user"),
                type=openapi.TYPE_INTEGER,
                required=True,
            ),
        ],
        responses={200: "Subscribed Successfully."},
    )
    @action(detail=False, methods=["post"], url_path="subscribe")
    def subscribe(self, request):
        categories = request.data.get("categories")
        email = request.data.get("email")

        if email is None:
            return Response(
                {"message": "missing param : Email can't be empty"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            user = User.objects.get(email=email)
        except:
            return Response(
                {"message": "User with this Email Id doesn't exist."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        sub_user = SubscribedUsers(user=user)
        sub_user.save()
        return Response(
            {"message": "Newsletter is successfully subscribed."},
            status=status.HTTP_200_OK,
        )
