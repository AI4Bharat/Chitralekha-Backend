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
from .models import NEWSLETTER_CATEGORY, Newsletter, SubscribedUsers
from .serializers import NewsletterSerializer
from users.models import User
from rest_framework.response import Response
from rest_framework import status
import logging
from django.http import HttpResponse
import requests
from django.http import HttpRequest
from organization.decorators import is_admin
from django.shortcuts import render
from django.template import loader
from django.http import HttpResponse
from django import template
from pathlib import Path
import os
from bs4 import BeautifulSoup
from django.core.mail import send_mail
from django.conf import settings


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
        content = request.data.get("content_1")
        submitter_id = request.data.get("submitter_id")
        template_id = request.data.get("template_id")
        BASE_DIR = Path(__file__).resolve().parent.parent

        if template_id == 1:
            if content != list or len(content) != 0:
                final_html_content = ""
                for c in content:
                    header_variable = c["header"]
                    paragraph_variable = c["paragraph"]
                    print(header_variable)
                    html_content = """<tr><td align="left" style="font-size:0px;padding:10px 25px;word-break:break-word;"><div style="font-family:Muli, Arial, sans-serif;font-size:20px;font-weight:400;line-height:30px;text-align:left;color:#333333;"><h1 style="margin: 0; font-size: 24px; line-height: normal; font-weight: bold;">{header}</h1></div></td></tr><tr><td style="font-size:0px;padding:10px 25px;word-break:break-word;"><p style="border-top: solid 1px #F4F5FB; font-size: 1px; margin: 0px auto; width: 100%;"></p></td></tr><tr><td align="left" style="font-size:0px;padding:10px 25px;word-break:break-word;"><div style="font-family:Muli, Arial, sans-serif;font-size:16px;font-weight:400;line-height:20px;text-align:left;color:#333333;"><p style="margin: 0;">{paragraph}</p></div></td></tr>""".format(
                        header=header_variable, paragraph=paragraph_variable
                    )
                    final_html_content = final_html_content + html_content
                requested_html = os.path.join(
                    BASE_DIR, "newsletter", "templates", "cl_newsletter_1.html"
                )
                file_html = open(
                    os.path.join(BASE_DIR, "newsletter", "templates", "variable.html"),
                    "w",
                )
                soup = BeautifulSoup(final_html_content, "html.parser")
                file_html.write(soup.prettify())
                context = {"variable": ""}
                file_html.close()
                html_file = loader.get_template(requested_html)
                html_content = html_file.render(context, request)
        elif template_id == 2:
            if content != list or len(content) != 0:
                final_html_content = ""
                for c in content:
                    header_variable = c["header"]
                    paragraph_variable = c["paragraph"]
                    video_poster = c["image"]
                    src = c["video"]
                    html_content = """<tr><td style="width:40%;text-align:center;"><div style="font-family:Muli, Arial, sans-serif;font-size:16px;text-align:center;color:#333333;"><video poster={video_poster} style="border:0;display:block;outline:none;text-decoration:none;height:auto;width:220px;font-size:13px;margin-left:20px;" width="45" controls="controls"><source src={src} type="video/mp4" /><a href="https://www.youtube.com/watch?v=QpeQx8bE598"><img src={video_poster} style="border:0;display:block;outline:none;text-decoration:none;height:auto;width:400px;font-size:13px;margin-left:220px;" width="45" alt="image instead of video" /></a></div></td><td style="font-size:0px;padding:10px 25px;word-break:break-word;"><div style="font-family:Muli, Arial, sans-serif;font-size:16px;font-weight:400;line-height:20px;color:#333333;"><h3>{header}</h3><p style="margin-left: 0px;">{paragraph}</p></div></td></tr>""".format(
                        header=header_variable,
                        video_poster=video_poster,
                        src=src,
                        paragraph=paragraph_variable,
                    )
                    final_html_content = final_html_content + html_content
                requested_html = os.path.join(
                    BASE_DIR, "newsletter", "templates", "cl_newsletter_1.html"
                )
                file_html = open(
                    os.path.join(BASE_DIR, "newsletter", "templates", "variable.html"),
                    "w",
                )
                soup = BeautifulSoup(final_html_content, "html.parser")
                file_html.write(soup.prettify())
                context = {"variable": ""}
                file_html.close()
                html_file = loader.get_template(requested_html)
                html_content = html_file.render(context, request)
        else:
            return Response(
                {"message": "Template not supported."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if content is None or content == "":
            return Response(
                {"message": "missing param : content can't be empty"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        new_newsletter = Newsletter(
            content=html_content,
            submitter_id=User.objects.get(pk=submitter_id),
            category="NEW_FEATURE",
        )
        new_newsletter.save()
        return Response(
            {"message": "Newsletter is successfully submitted."},
            status=status.HTTP_200_OK,
        )

    @swagger_auto_schema(
        method="post",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                "email": openapi.Schema(type=openapi.TYPE_STRING),
                "newsletter_id": openapi.Schema(
                    type=openapi.TYPE_STRING,
                ),
            },
            required=["email"],
        ),
        responses={200: "Subscribed Successfully."},
    )
    @action(detail=False, methods=["post"], url_path="send_mail_temp")
    def send_mail_temp(self, request):
        newsletter_id = request.data.get("newsletter_id")
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
        newsletter = Newsletter.objects.filter(newsletter_uuid=newsletter_id).first()
        print(newsletter.content)
        send_mail(
            "E-Newsletter November",
            "",
            settings.DEFAULT_FROM_EMAIL,
            [email],
            html_message=newsletter.content,
        )
        return Response(
            {"message": "Newsletter is successfully sent."},
            status=status.HTTP_200_OK,
        )

    @swagger_auto_schema(
        method="post",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                "email": openapi.Schema(type=openapi.TYPE_STRING),
            },
            required=["email"],
        ),
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
