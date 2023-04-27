import urllib
import requests

import os
import google.auth
import googleapiclient.discovery

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.oauth2.credentials import Credentials
from googleapiclient.http import MediaFileUpload, MediaIoBaseUpload

from google_auth_oauthlib.flow import InstalledAppFlow

from drf_yasg import openapi
from rest_framework.decorators import action
from drf_yasg.utils import swagger_auto_schema
from django.http import HttpRequest
from task.models import Task
from task.serializers import TaskSerializer
from mutagen.mp3 import MP3
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.permissions import IsAuthenticatedOrReadOnly
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet
from transcript.models import ORIGINAL_SOURCE, Transcript
from translation.models import Translation
from project.decorators import is_project_owner
from task.views import TaskViewSet
from task.serializers import TaskStatusSerializer
from .serializers import YoutubeSerializer
from django.utils import timezone
from django.http import HttpResponse
import io
import zipfile
from project.models import Project
from youtube.models import Youtube
from video.models import Video
import logging
import datetime
from datetime import timedelta
from urllib.parse import urlparse, parse_qs


@swagger_auto_schema(
    method="post",
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        properties={
            "youtube_id": openapi.Schema(type=openapi.TYPE_INTEGER),
        },
        required=["youtube_id"],
    ),
    responses={
        204: "Youtube auth revoked successfully.",
    },
)
@api_view(["POST"])
def revoke_access_token(request):
    youtube_id = request.data.get("youtube_id")

    if youtube_id is None:
        return Response(
            {"message": "missing param : youtube_id"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        youtube = Youtube.objects.get(pk=youtube_id)
    except Youtube.DoesNotExist:
        return Response(
            {"message": "Access token not found"}, status=status.HTTP_404_NOT_FOUND
        )

    youtube.delete()

    return Response(
        {"message": "Auth token deleted successfully."}, status=status.HTTP_200_OK
    )


@swagger_auto_schema(
    method="post",
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        properties={
            "project_id": openapi.Schema(type=openapi.TYPE_INTEGER),
            "channel_id": openapi.Schema(type=openapi.TYPE_STRING),
            "auth_token": openapi.Schema(type=openapi.TYPE_OBJECT),
        },
        required=["project_id", "channel_id", "auth_token"],
    ),
    responses={
        204: "Access token stored successfully.",
    },
)
@api_view(["POST"])
def store_access_token(request):
    """
    API Endpoint to store parameter of youtube
    Endpoint: /youtube/store_access_token/
    Method: POST
    """
    project_id = request.data.get("project_id")
    channel_id = request.data.get("channel_id")
    auth_token = request.data.get("auth_token")

    try:
        project = Project.objects.get(pk=project_id)
    except Project.DoesNotExist:
        return Response(
            {"message": "Project doesn't exist."},
            status=status.HTTP_404_NOT_FOUND,
        )

    try:
        new_youtube_auth = Youtube(
            project_id=project,
            channel_id=channel_id,
            auth_token=auth_token,
        )
        new_youtube_auth.save()

        return Response(
            {
                "message": "Youtube auth token saved successfully.",
            },
            status=status.HTTP_200_OK,
        )
    except Youtube.DoesNotExist:
        return Response(
            {"message": "Youtube not found"}, status=status.HTTP_404_NOT_FOUND
        )


@swagger_auto_schema(
    method="post",
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        properties={
            "video_id": openapi.Schema(type=openapi.TYPE_INTEGER),
        },
        required=["video_id"],
    ),
    responses={
        204: "Video caption stored successfully.",
    },
)
@api_view(["POST"])
def upload_to_youtube(request):
    """
    API Endpoint to store parameter of youtube
    Endpoint: /youtube/upload_to_youtube/
    Method: PATCH
    """

    # Replace with your API key or OAuth 2.0 credentials
    API_KEY = "AIzaSyCJdbxZL91wXN-77-bbm6kEjyh4HaFr78Y"

    # Create a YouTube API client
    youtube = build("youtube", "v3", developerKey=API_KEY)

    # Specify the video ID
    get_video_id = request.data.get("video_id")
    video = Video.objects.get(pk=get_video_id)

    video_url = video.url
    parsed_url = urlparse(video_url)
    video_id = parse_qs(parsed_url.query)["v"][0]

    # Call the "videos.list" method to retrieve video information
    videos_response = youtube.videos().list(part="snippet", id=video_id).execute()

    # Extract the channel ID from the response
    video = videos_response.get("items", [])[0]
    channel_id = video["snippet"]["channelId"]

    # By channel id, get auth token from database
    youtube_auth = Youtube.objects.filter(channel_id=channel_id).first()
    if youtube_auth is None:
        return Response(
            {"message": "Youtube auth not found."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Define the path to your credentials file
    CREDENTIALS_FILE = youtube_auth.auth_token

    # Define the ID of the YouTube video you want to upload a subtitle file for
    VIDEO_ID = video_id

    # Define the path to the subtitle file you want to upload
    # DOWNLOAD completed file, extract and upload to azure
    SUBTITLE_FILE = "/home/vipul/Downloads/Chitralekha_Video77_20230411_171438_hi.srt"

    # Define the language of the subtitle file (ISO 639-1 language code)
    LANGUAGE = "hi"

    # Define the YouTube API service object
    creds = None

    if CREDENTIALS_FILE:
        creds = Credentials.from_authorized_user_info(
            CREDENTIALS_FILE,
            scopes=["https://www.googleapis.com/auth/youtube.force-ssl"],
        )

    # # Define the path to your credentials file
    # CREDENTIALS_FILE = '/home/vipul/Documents/projects/chitralekha_backend/Chitralekha-Backend/google-desktop.json'

    # if os.path.exists(CREDENTIALS_FILE):
    #     creds = Credentials.from_authorized_user_file(CREDENTIALS_FILE, scopes=['https://www.googleapis.com/auth/youtubepartner'])

    # Define the path to your client secret file
    # CLIENT_SECRET_FILE = '/home/vipul/Documents/projects/chitralekha_backend/Chitralekha-Backend/google-web.json'
    # scopes = ['https://www.googleapis.com/auth/youtube.force-ssl']
    # if not creds or not creds.valid:
    #     flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET_FILE, scopes=scopes)
    #     creds = flow.run_local_server(port=0)
    #     with open(CREDENTIALS_FILE, 'w') as f:
    #         f.write(creds.to_json())

    youtube = build("youtube", "v3", credentials=creds)

    # Upload the caption file
    try:
        insert_request = (
            youtube.captions()
            .insert(
                part="snippet",
                body=dict(
                    snippet=dict(
                        videoId=VIDEO_ID, language=LANGUAGE, name="Manually-generated"
                    )
                ),
                media_body=MediaFileUpload(
                    SUBTITLE_FILE, mimetype="application/octet-stream", resumable=True
                ),
            )
            .execute()
        )

        logging.info(
            "The caption track has been added with ID %s." % insert_request["id"]
        )
        return Response(
            {
                "message": "Caption track has been added",
            },
            status=status.HTTP_200_OK,
        )
    except HttpError as e:
        logging.info("An HTTP error %d occurred:\n%s" % (e.resp.status, e.content))
        return Response({"message": e.reason}, status=status.HTTP_404_NOT_FOUND)


def get_completed_transcript(video_id, export_type):
    video = Video.objects.get(id=video_id)
