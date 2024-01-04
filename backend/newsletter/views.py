from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import status
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.permissions import AllowAny
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
from .tasks import celery_newsletter_call
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
import uuid
from django.shortcuts import render
import base64
from html.parser import HTMLParser
from config import app_name


@swagger_auto_schema(
    method="get",
    manual_parameters=[
        openapi.Parameter(
            "email",
            openapi.IN_QUERY,
            description=("Email of user"),
            type=openapi.TYPE_STRING,
            required=False,
        ),
        openapi.Parameter(
            "categories",
            openapi.IN_QUERY,
            description=("categories"),
            type=openapi.TYPE_OBJECT,
            required=False,
        ),
    ],
    responses={200: "Unsubscribed successfully."},
)
@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def unsubscribe(request):
    email = request.GET.get("email")
    try:
        sub_user = SubscribedUsers.objects.get(email=email)
    except SubscribedUsers.DoesNotExist:
        return Response(
            {"message": "User is not subscribed."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    categories = request.GET.get("categories")
    sub_user.subscribed_categories = categories.split(',')
    sub_user.save()
    return Response(
        {"message": "User unsubscribed successfully."},
        status=status.HTTP_200_OK,
    )


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
        template_id = request.data.get("template_id")
        subject = request.data.get("subject")
        BASE_DIR = Path(__file__).resolve().parent.parent

        if content is None or content == "":
            return Response(
                {"message": "missing param : content can't be empty"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if subject is None or len(subject) == 0:
            subject = f"{app_name} Newsletter"
        else:
            subject = subject
        if template_id == 1:
            if len(content) != 0:
                final_html_content = ""
                for c in content:
                    header_variable = c["header"]
                    paragraph_variable = c["paragraph"]
                    html_content = """<tr><td align="left" style="font-size:0px;padding:10px 25px;word-break:break-word;"><div style="font-family:Muli, Arial, sans-serif;font-size:20px;font-weight:400;line-height:30px;text-align:left;color:#333333;"><h1 style="margin: 0; font-size: 24px; line-height: normal; font-weight: bold;">{header}</h1></div></td></tr><tr><td style="font-size:0px;padding:10px 25px;word-break:break-word;"><p style="border-top: solid 1px #F4F5FB; font-size: 1px; margin: 0px auto; width: 100%;"></p></td></tr><tr><td align="left" style="font-size:0px;padding:10px 25px;word-break:break-word;"><div style="font-family:Muli, Arial, sans-serif;font-size:16px;font-weight:400;line-height:20px;text-align:left;color:#333333;"><p style="margin: 0;">{paragraph}</p></div></td></tr>""".format(
                        header=header_variable, paragraph=paragraph_variable
                    )
                    final_html_content = final_html_content + html_content
                requested_html = os.path.join(
                    BASE_DIR, "newsletter", "templates", "cl_newsletter_1.html"
                )
                uuid_num = str(uuid.uuid4())
                temp_file = "variable_" + uuid_num + ".html"
                file_html = open(
                    os.path.join(BASE_DIR, "newsletter", "templates", temp_file), "w"
                )
                soup = BeautifulSoup(final_html_content, "html.parser")
                file_html.write(soup.prettify())
                dynamic_template_name = temp_file
                context = {"dynamic_template_name": dynamic_template_name}
                file_html.close()
                html_file = loader.get_template(requested_html)
                html_content = html_file.render(context, request)
                html_file = ""
        elif template_id == 2:
            if len(content) != 0:
                final_html_content = ""
                for c in content:
                    header_variable = c["header"]
                    paragraph_variable = c["paragraph"]
                    video_poster = c["image"]
                    youtube_url = c["youtube_url"]
                    html_content = """<tr><td style="width:40%;text-align:center;"><div style="font-family:Muli, Arial, sans-serif;font-size:16px;text-align:center;color:#333333;"><a href={youtube_url}><img src={video_poster} style="border:0;display:block;outline:none;text-decoration:none;height:auto;width:220px;font-size:13px;margin-left:20px;" width="45" alt="image instead of video" /></a></div></td><td style="font-size:0px;padding:10px 25px;word-break:break-word;"><div style="font-family:Muli, Arial, sans-serif;font-size:16px;font-weight:400;line-height:20px;color:#333333;"><h3>{header}</h3><p style="margin-left: 0px;">{paragraph}</p></div></td></tr>""".format(
                        header=header_variable,
                        video_poster=video_poster,
                        youtube_url=youtube_url,
                        paragraph=paragraph_variable,
                    )
                    final_html_content = final_html_content + html_content
                requested_html = os.path.join(
                    BASE_DIR, "newsletter", "templates", "cl_newsletter_1.html"
                )
                uuid_num = str(uuid.uuid4())
                temp_file = "variable_" + uuid_num + ".html"
                file_html = open(
                    os.path.join(BASE_DIR, "newsletter", "templates", temp_file), "w"
                )
                soup = BeautifulSoup(final_html_content, "html.parser")
                file_html.write(soup.prettify())
                dynamic_template_name = temp_file
                context = {"dynamic_template_name": dynamic_template_name}
                file_html.close()
                html_file = loader.get_template(requested_html)
                html_content = html_file.render(context, request)
                html_file = ""
        elif template_id == 3:
            if type(content) == dict:
                message = base64.b64decode(content["html"]).decode("utf-8")
                f = open("content.html", "w")
                f.write(message)
                f.close()

                html_content = message
        else:
            return Response(
                {"message": "Template not supported."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        new_newsletter = Newsletter(
            content=html_content,
            submitter_id=User.objects.get(pk=submitter_id),
            category=category,
        )
        new_newsletter.save()
        html_content_f = html_content
        html_content = ""
        try:
            os.remove(os.path.join(BASE_DIR, "newsletter", "templates", temp_file))
        except:
            print("Error in Removing files.")
        celery_newsletter_call.delay(new_newsletter.id, subject)
        return Response(
            {"message": "Newsletter is successfully submitted."},
            status=status.HTTP_200_OK,
        )

    @is_admin
    @swagger_auto_schema(request_body=NewsletterSerializer)
    @action(detail=False, methods=["post"], url_path="preview")
    def preview(self, request, pk=None, *args, **kwargs):
        category = request.data.get("category")
        content = request.data.get("content")
        submitter_id = request.data.get("submitter_id")
        template_id = request.data.get("template_id")
        BASE_DIR = Path(__file__).resolve().parent.parent

        if content is None or content == "":
            return Response(
                {"message": "missing param : content can't be empty"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if template_id == 1:
            if len(content) != 0:
                final_html_content = ""
                for c in content:
                    header_variable = c["header"]
                    paragraph_variable = c["paragraph"]
                    html_content = """<tr><td align="left" style="font-size:0px;padding:10px 25px;word-break:break-word;"><div style="font-family:Muli, Arial, sans-serif;font-size:20px;font-weight:400;line-height:30px;text-align:left;color:#333333;"><h1 style="margin: 0; font-size: 24px; line-height: normal; font-weight: bold;">{header}</h1></div></td></tr><tr><td style="font-size:0px;padding:10px 25px;word-break:break-word;"><p style="border-top: solid 1px #F4F5FB; font-size: 1px; margin: 0px auto; width: 100%;"></p></td></tr><tr><td align="left" style="font-size:0px;padding:10px 25px;word-break:break-word;"><div style="font-family:Muli, Arial, sans-serif;font-size:16px;font-weight:400;line-height:20px;text-align:left;color:#333333;"><p style="margin: 0;">{paragraph}</p></div></td></tr>""".format(
                        header=header_variable, paragraph=paragraph_variable
                    )
                    final_html_content = final_html_content + html_content
                requested_html = os.path.join(
                    BASE_DIR, "newsletter", "templates", "cl_newsletter_1.html"
                )
                uuid_num = str(uuid.uuid4())
                temp_file = "variable_" + uuid_num + ".html"
                file_html = open(
                    os.path.join(BASE_DIR, "newsletter", "templates", temp_file), "w"
                )
                soup = BeautifulSoup(final_html_content, "html.parser")
                file_html.write(soup.prettify())
                dynamic_template_name = temp_file
                context = {"dynamic_template_name": dynamic_template_name}
                file_html.close()
                html_file = loader.get_template(requested_html)
                html_content = html_file.render(context, request)
                html_file = ""
        elif template_id == 2:
            if len(content) != 0:
                final_html_content = ""
                for c in content:
                    header_variable = c["header"]
                    paragraph_variable = c["paragraph"]
                    video_poster = c["image"]
                    youtube_url = c["youtube_url"]
                    html_content = """<tr><td style="width:40%;text-align:center;"><div style="font-family:Muli, Arial, sans-serif;font-size:16px;text-align:center;color:#333333;"><a href={youtube_url}><img src={video_poster} style="border:0;display:block;outline:none;text-decoration:none;height:auto;width:220px;font-size:13px;margin-left:20px;" width="45" alt="image instead of video" /></a></div></td><td style="font-size:0px;padding:10px 25px;word-break:break-word;"><div style="font-family:Muli, Arial, sans-serif;font-size:16px;font-weight:400;line-height:20px;color:#333333;"><h3>{header}</h3><p style="margin-left: 0px;">{paragraph}</p></div></td></tr>""".format(
                        header=header_variable,
                        video_poster=video_poster,
                        youtube_url=youtube_url,
                        paragraph=paragraph_variable,
                    )
                    final_html_content = final_html_content + html_content
                requested_html = os.path.join(
                    BASE_DIR, "newsletter", "templates", "cl_newsletter_1.html"
                )
                uuid_num = str(uuid.uuid4())
                temp_file = "variable_" + uuid_num + ".html"
                file_html = open(
                    os.path.join(BASE_DIR, "newsletter", "templates", temp_file), "w"
                )
                soup = BeautifulSoup(final_html_content, "html.parser")
                file_html.write(soup.prettify())
                dynamic_template_name = temp_file
                context = {"dynamic_template_name": dynamic_template_name}
                file_html.close()
                html_file = loader.get_template(requested_html)
                html_content = html_file.render(context, request)
                html_file = ""
        elif template_id == 3:
            if len(content) != 0:
                message = base64.b64decode(content).decode("utf-8")
                f = open("content.html", "w")
                f.write(message)
                f.close()
                html_content = message
        else:
            return Response(
                {"message": "Template not supported."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        html_content_f = html_content
        html_content = ""
        try:
            os.remove(os.path.join(BASE_DIR, "newsletter", "templates", temp_file))
        except:
            print("Error in Removing files.")
        return Response(
            {"html": html_content_f},
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
        for subscribed_user in SubscribedUsers.objects.all():
            subscribed_user.email = subscribed_user.user.email
            subscribed_user.subscribed_categories = ["Release", "Downtime", "General"]
            subscribed_user.save()
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
        send_mail(
            f"{app_name} E-Newsletter",
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
        method="patch",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                "email": openapi.Schema(type=openapi.TYPE_STRING),
                "user_id": openapi.Schema(type=openapi.TYPE_INTEGER),
                "categories": openapi.Schema(type=openapi.TYPE_OBJECT),
            },
            required=["email", "user_id"],
        ),
        responses={200: "Categories updated successfully."},
    )
    @action(detail=False, methods=["patch"], url_path="update_subscription")
    def update_subscription(self, request):
        categories = request.data.get("categories")
        email = request.data.get("email")
        user_id = request.data.get("user_id")
        subscribe = request.data.get("subscribe", True)

        if email is None or user_id is None:
            return Response(
                {"message": "missing param : Email or user_id can't be empty"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            user = User.objects.get(pk=user_id)
        except:
            return Response(
                {"message": "User with this Email Id doesn't exist."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if subscribe == True:
            sub_user = SubscribedUsers.objects.get(user=user)
            if sub_user is None:
                SubscribedUsers.objects.create(
                    user=user, email=email, subscribed_categories=categories
                )
            else:
                subscribed_categories = ",".join(sub_user.subscribed_categories)
                sub_user.subscribed_categories = categories
                sub_user.save()

        return Response(
            {"message": "Subscription is updated successfully."},
            status=status.HTTP_200_OK,
        )

    @swagger_auto_schema(
        method="patch",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                "email": openapi.Schema(type=openapi.TYPE_STRING),
                "user_id": openapi.Schema(type=openapi.TYPE_INTEGER),
            },
            required=["email", "user_id"],
        ),
        responses={200: "Subscribed Successfully."},
    )
    @action(detail=False, methods=["patch"], url_path="update_email")
    def update_email(self, request):
        categories = request.data.get("categories")
        email = request.data.get("email")
        user_id = request.data.get("user_id")

        if email is None or user_id is None:
            return Response(
                {"message": "missing param : Email or user_id can't be empty"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            user = User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return Response(
                {"message": "This user does not exist."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            sub_user = SubscribedUsers.objects.get(user=user)
        except SubscribedUsers.DoesNotExist:
            return Response(
                {"message": "User is not subscribed."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if sub_user.email == email:
            return Response(
                {"message": "Already subscribed with this email."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        sub_user.email = email
        sub_user.save()
        return Response(
            {"message": "Email is updated successfully."},
            status=status.HTTP_200_OK,
        )
