import urllib
import requests

import os
import google.auth
import googleapiclient.discovery

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.oauth2.credentials import Credentials
from googleapiclient.http import MediaFileUpload, MediaIoBaseUpload
from google.auth.transport.requests import Request

from google_auth_oauthlib.flow import InstalledAppFlow

from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.permissions import IsAuthenticatedOrReadOnly
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from drf_yasg import openapi
from rest_framework.decorators import action
from drf_yasg.utils import swagger_auto_schema
from django.http import HttpRequest
from task.models import Task
from task.serializers import TaskSerializer
from mutagen.mp3 import MP3
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
from config import youtube_api_key, frontend_url
from .utils import *
from video.utils import *

from pathlib import Path
import html2text

BASE_DIR = Path(__file__).resolve().parent.parent


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
            "auth_token": openapi.Schema(type=openapi.TYPE_OBJECT),
        },
        required=["project_id", "auth_token"],
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
    auth_token = request.data.get("auth_token")

    try:
        project = Project.objects.get(pk=project_id)
    except Project.DoesNotExist:
        return Response(
            {"message": "Project doesn't exist."},
            status=status.HTTP_404_NOT_FOUND,
        )

    url = "https://oauth2.googleapis.com/token"
    auth_code = auth_token["refresh_token"]
    data = {
        "code": auth_code,
        "client_id": auth_token["client_id"],
        "client_secret": auth_token["client_secret"],
        "redirect_uri": frontend_url,
        "grant_type": "authorization_code",
    }

    response = requests.post(url=url, json=data)

    if response.status_code == 200:
        logging.info("response %s", response.content)
        response_token = json.loads(response.content.decode("utf-8"))
        auth_token["refresh_token"] = response_token["refresh_token"]
        auth_token["access_token"] = response_token["access_token"]
        auth_token["code"] = auth_code

        # Get the authenticated user's credentials from the Django session
        credentials = Credentials.from_authorized_user_info(auth_token)

        # Create a YouTube API client
        youtube = build("youtube", "v3", credentials=credentials)

        try:
            # Call the 'channels.list' method to retrieve the list of channels
            channels_response = (
                youtube.channels().list(part="snippet", mine=True).execute()
            )

            # Extract the channel information from the API response
            channels = channels_response["items"]

            for channel in channels:
                channel_id = channel["id"]

                authExist = (
                    Youtube.objects.filter(project_id=project_id)
                    .filter(channel_id=channel_id)
                    .first()
                )

                if authExist:
                    Youtube.objects.filter(pk=authExist.id).update(
                        auth_token=auth_token
                    )
                else:
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
        except HttpError as e:
            logging.info("An HTTP error %d occurred:\n%s" % (e.resp.status, e.content))
            return Response({"message": e.reason}, status=e.resp.status)

    else:
        return Response({"message": response.content}, status=response.status_code)


@swagger_auto_schema(
    method="post",
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        properties={
            "task_ids": openapi.Schema(
                type=openapi.TYPE_OBJECT,
                description="List of task ids to be uploaded.",
            ),
            "export_type": openapi.Schema(
                type=openapi.TYPE_STRING,
                description="Export Type of Transcript. Default is srt.",
            ),
        },
        required=["task_ids"],
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

    task_responses = []
    # get request parameters
    get_task_ids = request.data.get("task_ids")
    export_type = request.data.get("export_type")
    if (type(get_task_ids) is list) and len(get_task_ids) > 0:
        # Iterating over task ids
        for get_task_id in get_task_ids:
            response_obj = {
                "task_id": get_task_id,
                "video_name": "",
                "video_url": "",
                "task_type": "",
                "source_language": "",
                "target_language": "",
                "status": "",
                "message": "",
            }

            try:
                task_obj = Task.objects.get(pk=get_task_id)
            except Task.DoesNotExist:
                response_obj["status"] = "Fail"
                response_obj["message"] = "Task Not Found."
                task_responses.append(response_obj)
                continue

            # get video_id from task
            video_id = task_obj.video_id
            video = Video.objects.get(pk=video_id)

            # Get translation/transcript and generate srt file, upload to blob storage
            try:
                request.data["return_file_content"] = True
                file_is_exportable = False

                response_obj["video_name"] = video.name
                response_obj["video_url"] = video.url
                response_obj["task_type"] = task_obj.get_task_type_label
                response_obj["source_language"] = task_obj.get_src_language_label
                response_obj["target_language"] = task_obj.get_target_language_label

                # check transcript is exportable or not
                if (
                    task_obj.task_type == "TRANSCRIPTION_REVIEW"
                    and task_obj.status == "COMPLETE"
                ):
                    file_is_exportable = True
                elif (
                    task_obj.task_type == "TRANSCRIPTION_EDIT"
                    and task_obj.status == "COMPLETE"
                ):
                    review_exist = (
                        Task.objects.filter(video_id=video_id)
                        .filter(task_type="TRANSCRIPTION_REVIEW")
                        .first()
                    )
                    if review_exist is None:
                        file_is_exportable = True

                # check transcript is exportable or not
                if (
                    task_obj.task_type == "TRANSLATION_REVIEW"
                    and task_obj.status == "COMPLETE"
                ):
                    file_is_exportable = True
                elif (
                    task_obj.task_type == "TRANSLATION_EDIT"
                    and task_obj.status == "COMPLETE"
                ):
                    SUBTITLE_LANG = task_obj.target_language
                    review_exist = (
                        Task.objects.filter(video_id=video_id)
                        .filter(task_type="TRANSLATION_REVIEW")
                        .filter(target_language=SUBTITLE_LANG)
                        .first()
                    )
                    if review_exist is None:
                        file_is_exportable = True

                if file_is_exportable:
                    if task_obj.task_type in ["TRANSLATION_REVIEW", "TRANSLATION_EDIT"]:
                        target_lang_content = get_export_translation(
                            request, get_task_id, "srt"
                        )
                        SUBTITLE_LANG = task_obj.target_language
                    elif task_obj.task_type in [
                        "TRANSCRIPTION_REVIEW",
                        "TRANSCRIPTION_EDIT",
                    ]:
                        if export_type is None:
                            export_type = "srt"
                        target_lang_content = get_export_transcript(
                            request, get_task_id, export_type
                        )

                        SUBTITLE_LANG = video.language
                    else:
                        response_obj["status"] = "Fail"
                        response_obj["message"] = "Invalid task type."
                        task_responses.append(response_obj)
                        continue

                    if export_type == "ytt":
                        file_name = str(task_obj.id) + "_" + SUBTITLE_LANG + ".ytt"
                        caption_file = target_lang_content.data["file_location"]
                    else:
                        serialized_data = json.loads(
                            target_lang_content.content.decode("utf-8")
                        )
                        file_name = str(task_obj.id) + "_" + SUBTITLE_LANG + ".srt"
                        caption_file = uploadToLocalDir(file_name, serialized_data)
                else:
                    response_obj["status"] = "Fail"
                    response_obj["message"] = "Please complete relevant tasks."
                    task_responses.append(response_obj)
                    continue
            except Exception as e:
                logging.info("An issue occured while exporting the subtitles.")
                response_obj["status"] = "Fail"
                error = html2text.html2text(e.args[0])
                response_obj["message"] = error
                task_responses.append(response_obj)
                continue

            try:
                # get channel id of video for requested taks
                video_url = video.url
                parsed_url = urlparse(video_url)
                video_id = parse_qs(parsed_url.query)["v"][0]

                # Replace with your API key or OAuth 2.0 credentials
                API_KEY = youtube_api_key

                # Create a YouTube API client
                youtube = build("youtube", "v3", developerKey=API_KEY)

                # Call the "videos.list" method to retrieve video information
                videos_response = (
                    youtube.videos().list(part="snippet", id=video_id).execute()
                )

                # Extract the channel ID from the response
                video_obj_for_channel = videos_response.get("items", [])[0]
                if video_obj_for_channel is not None:
                    channel_id = video_obj_for_channel["snippet"]["channelId"]

                    # By channel id, get auth token from database
                    youtube_auth = (
                        Youtube.objects.filter(channel_id=channel_id)
                        .filter(project_id=video.project_id.id)
                        .first()
                    )
                    if youtube_auth is None:
                        response_obj["status"] = "Fail"
                        response_obj["message"] = "Youtube auth not found."
                        task_responses.append(response_obj)
                        continue

                else:
                    response_obj["status"] = "Fail"
                    response_obj[
                        "message"
                    ] = "Task's video is either deleted or not accessible"
                    continue

            except Exception as e:
                response_obj["status"] = "Fail"
                error = html2text.html2text(e.args[0])
                logging.info(error)
                response_obj["message"] = error
                task_responses.append(response_obj)
                continue

            # Upload the caption file
            try:
                # Define the path to your credentials file
                CREDENTIALS_FILE = youtube_auth.auth_token

                # Define the ID of the YouTube video you want to upload a subtitle file for
                VIDEO_ID = video_id

                # Define the path to the subtitle file you want to upload
                SUBTITLE_FILE = caption_file

                # Define the language of the subtitle file (ISO 639-1 language code)
                LANGUAGE = SUBTITLE_LANG

                if CREDENTIALS_FILE:
                    creds = Credentials.from_authorized_user_info(
                        CREDENTIALS_FILE,
                        scopes=["https://www.googleapis.com/auth/youtubepartner"],
                    )

                    # Check if the stored access token has expired
                    logging.info("creds.expired %s", str(creds.expired))
                    if creds.expired:
                        # Use the refresh token to obtain a new access token
                        url = "https://oauth2.googleapis.com/token"
                        headers = {"Content-Type": "x-www-form-urlencoded"}
                        data = {
                            "grant_type": "refresh_token",
                            "refresh_token": creds.refresh_token,
                            "client_id": creds.client_id,
                            "client_secret": creds.client_secret,
                        }
                        response = requests.post(url=url, headers=headers, json=data)
                        logging.info("response.content %s", str(response.content))
                        logging.info(
                            "response.status_code %s", str(response.status_code)
                        )
                        auth_content = response.content
                        auth_content_decode = auth_content.decode("utf-8")
                        auth_content_json = json.loads(auth_content_decode)

                        youtube_auth_reeuset_data = {
                            "client_id": creds.client_id,
                            "client_secret": creds.client_secret,
                            "refresh_token": auth_content_json["access_token"],
                        }
                        creds = Credentials.from_authorized_user_info(
                            youtube_auth_reeuset_data,
                            scopes=["https://www.googleapis.com/auth/youtubepartner"],
                        )
                        logging.info("Re-Generated credential")

                youtube = build("youtube", "v3", credentials=creds)
                insert_request = (
                    youtube.captions()
                    .insert(
                        part="snippet",
                        body=dict(
                            snippet=dict(
                                videoId=VIDEO_ID,
                                language=LANGUAGE,
                                name="Manually-generated",
                            )
                        ),
                        media_body=MediaFileUpload(
                            SUBTITLE_FILE,
                            mimetype="application/octet-stream",
                            resumable=True,
                        ),
                    )
                    .execute()
                )

                # Delete file from local directory
                os.remove(caption_file)

                logging.info(
                    "The caption track has been added with ID %s."
                    % insert_request["id"]
                )
                response_obj["status"] = "Success"
                response_obj[
                    "message"
                ] = "Successfully caption is added to youtube video"

                task_responses.append(response_obj)
                continue

            except HttpError as e:
                logging.info(
                    "An HTTP error %d occurred:\n%s" % (e.resp.status, e.reason)
                )
                response_obj["status"] = "Fail"
                logging.info("e.reason")
                error = html2text.html2text(e.reason)
                logging.info(error)
                response_obj["message"] = error
                task_responses.append(response_obj)
                continue
            except Exception as e:
                response_obj["status"] = "Fail"
                logging.info("e args")
                error = html2text.html2text(e.args[0])
                logging.info(error)
                response_obj["message"] = error
                task_responses.append(response_obj)
                continue

        return Response(task_responses, status=status.HTTP_200_OK)

    else:
        return Response(
            {"message": "Missing Params: task_ids"},
            status=status.HTTP_400_BAD_REQUEST,
        )
