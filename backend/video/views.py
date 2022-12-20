import urllib
from datetime import timedelta
import requests
from drf_yasg import openapi
from rest_framework.decorators import action
from drf_yasg.utils import swagger_auto_schema
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
from .models import Video
from .serializers import VideoSerializer
from .utils import (
    get_data_from_google_video,
    get_subtitles_from_google_video,
    drive_info_extractor,
    DownloadError,
)
from project.models import Project


@swagger_auto_schema(
    method="post",
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        properties={
            "video_id": openapi.Schema(type=openapi.TYPE_OBJECT),
        },
        required=["video_id"],
    ),
    responses={
        204: "Video deleted successfully.",
    },
)
@api_view(["POST"])
def delete_video(request):
    video_id = request.data.get("video_id")

    if video_id is None:
        return Response(
            {"message": "missing param : video_id"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        video = Video.objects.get(pk=video_id)
    except Video.DoesNotExist:
        return Response(
            {"message": "Video not found"}, status=status.HTTP_404_NOT_FOUND
        )

    video.delete()

    return Response(
        {"message": "Video deleted successfully."}, status=status.HTTP_200_OK
    )


@swagger_auto_schema(
    method="get",
    manual_parameters=[
        openapi.Parameter(
            "multimedia_url",
            openapi.IN_QUERY,
            description=(
                "A string to pass the url of the video/audio file to be transcribed"
            ),
            type=openapi.TYPE_STRING,
            required=True,
        ),
        openapi.Parameter(
            "lang",
            openapi.IN_QUERY,
            description=(
                "A string to pass the language in which the video should be transcribed"
            ),
            type=openapi.TYPE_STRING,
            required=True,
        ),
        openapi.Parameter(
            "project_id",
            openapi.IN_QUERY,
            description=("Id of the project to which this video belongs"),
            type=openapi.TYPE_INTEGER,
            required=True,
        ),
        openapi.Parameter(
            "description",
            openapi.IN_QUERY,
            description=("A string to give description about video"),
            type=openapi.TYPE_STRING,
            required=False,
        ),
        openapi.Parameter(
            "is_audio_only",
            openapi.IN_QUERY,
            description=(
                "A boolean to pass whether the user submitted a video or audio"
            ),
            type=openapi.TYPE_BOOLEAN,
            required=False,
        ),
    ],
    responses={200: "Return the video subtitle payload"},
)
@api_view(["GET"])
def get_video(request):
    """
    API Endpoint to get the direct URL to a video
    Endpoint: /video/
    Method: GET
    Query Params: multimedia_url (required)
    """

    # Get the video URL from the query params
    url = request.query_params.get("multimedia_url")
    lang = request.query_params.get("lang", "en")
    project_id = request.query_params.get("project_id")
    description = request.query_params.get("description", "")
    is_audio_only = request.query_params.get("is_audio_only", "false")

    # Convert audio only to boolean
    is_audio_only = is_audio_only.lower() == "true"
    if not url:
        return Response(
            {"error": "Video URL not provided in query params."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    project = Project.objects.filter(pk=project_id).first()
    if project is None:
        return Response(
            {"error": "Project is not found. "},
            status=status.HTTP_404_NOT_FOUND,
        )

    ## PATCH: Handle audio_only files separately for google drive links
    ## TODO: Move it to an util function
    if "drive.google.com" in url and is_audio_only:

        # Construct a direct download link from the google drive url
        # get the id from the drive link
        try:
            file_id = drive_info_extractor._match_id(url)
        except Exception:
            return Response(
                {"error": "Invalid Google Drive URL."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        url = f"https://drive.google.com/uc?export=download&confirm=yTib&id={file_id}"

        # Get the video metadata
        title = (
            urllib.request.urlopen(urllib.request.Request(url)).info().get_filename()
        )
        direct_audio_url = url

        # Calculate the duration
        filename, headers = urllib.request.urlretrieve(url)
        audio = MP3(filename)
        duration = timedelta(seconds=int(audio.info.length))

        # Create a new DB entry if URL does not exist, else return the existing entry
        video, created = Video.objects.get_or_create(
            url=url,
            defaults={
                "name": title,
                "duration": duration,
                "project_id": project,
                "audio_only": is_audio_only,
                "language": lang,
                "description": description,
            },
        )
        if created:
            video.save()
            return Response(
                {
                    "video": VideoSerializer(video).data,
                    "direct_audio_url": direct_audio_url,
                    "message": "Video successfully created.",
                },
                status=status.HTTP_200_OK,
            )
        else:
            return Response(
                {
                    "video": VideoSerializer(video).data,
                    "direct_audio_url": direct_audio_url,
                },
                status=status.HTTP_200_OK,
            )

    try:
        # Get the video info from the YouTube API
        (
            direct_video_url,
            normalized_url,
            title,
            duration,
            direct_audio_url,
        ) = get_data_from_google_video(url)
    except DownloadError:
        return Response(
            {"error": f"{url} is an invalid video URL."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Create a new DB entry if URL does not exist, else return the existing entry
    video, created = Video.objects.get_or_create(
        url=normalized_url,
        defaults={
            "name": title,
            "duration": duration,
            "project_id": project,
            "audio_only": is_audio_only,
            "language": lang,
            "description": description,
        },
    )
    if created:
        video.save()
        subtitle_payload, is_machine_generated = get_subtitles_from_google_video(
            url, lang
        )
        if subtitle_payload:
            # Save the subtitles to the video object
            video.subtitles = {
                # "status": "SUCCESS",
                "output": subtitle_payload,
            }
            video.save()

    # Create the response data to be returned
    video.audio_only = is_audio_only
    serializer = VideoSerializer(video)
    response_data = {
        "video": serializer.data,
    }

    # Check if it's audio only
    if is_audio_only:
        response_data["direct_audio_url"] = direct_audio_url
    else:
        response_data["direct_video_url"] = direct_video_url

    if created:
        response_data["message"] = "Video created successfully."
        return Response(
            response_data,
            status=status.HTTP_200_OK,
        )
    else:
        return Response(
            response_data,
            status=status.HTTP_200_OK,
        )


@swagger_auto_schema(
    method="get",
    manual_parameters=[
        openapi.Parameter(
            "is_audio_only",
            openapi.IN_QUERY,
            description=("A boolean to only return audio entries or video entries"),
            type=openapi.TYPE_BOOLEAN,
            required=True,
        ),
        openapi.Parameter(
            "count",
            openapi.IN_QUERY,
            description=("The number of entries to return"),
            type=openapi.TYPE_INTEGER,
            required=False,
        ),
    ],
    responses={200: "Return the video subtitle payload"},
)
@api_view(["GET"])
def list_recent(request):
    """
    API Endpoint to list the recent videos
    Endpoint: /video/list_recent/
    Method: GET
    """
    # Get the audio only param
    is_audio_only = request.query_params.get("is_audio_only", "false")
    is_audio_only = is_audio_only.lower() == "true"

    # Get the query param from the request, default count is 10
    count = int(request.query_params.get("count", 10))

    # Note: Currently, we have implemented this get recent method based on the logic that
    # one Transcript of either type ORIGINAL_SOURCE or type MACHINE_GENERATED
    # will always have one video associated with it.
    # In the future, if that constraint is removed then we might need to alter the logic.

    try:

        # Get the relevant videos, based on the audio only param
        video_list = Video.objects.filter(audio_only=is_audio_only)

        # Get the N latest transcripts from the DB for the user associated with the video_list
        recent_transcripts = [
            (transcript.video, transcript.updated_at, transcript.id)
            for transcript in Transcript.objects.filter(user=request.user.id)
            .filter(video__in=video_list)
            .order_by("-updated_at")[:count]
        ]

        # Get the date of the nth recently updated trancript from the above list
        least_recently_updated_transcript_date = recent_transcripts[-1][1]

        # Get the list of transcript IDs from recent translations
        filtered_transcript_ids = [transcript[2] for transcript in recent_transcripts]

        # Filter the translations by transcript IDs and
        # Get the latest translations from the DB for the user which are updated after the nth recently updated transcript
        recent_translations = [
            (
                translation.transcript.video,
                translation.updated_at,
                translation.transcript.id,
            )
            for translation in Translation.objects.filter(user=request.user.id)
            .filter(transcript__in=filtered_transcript_ids)
            .filter(updated_at__gt=least_recently_updated_transcript_date)
            .select_related("transcript")
            .order_by("-updated_at")
        ]

    except IndexError:
        # If there are no transcripts in the DB for the user
        return Response(
            {"message": "No recent videos found!"},
            status=status.HTTP_200_OK,
        )

    # Form a union of the lists and sort by updated_at
    union_list = recent_transcripts + recent_translations
    union_list.sort(key=lambda x: x[1], reverse=True)

    # Find the first N unique videos in the union list
    videos = []
    for video, date, _ in union_list:
        if len(videos) >= count:
            break
        if video not in videos:
            videos.append(video)

    # Fetch and return the videos
    serializer = VideoSerializer(videos, many=True)
    return Response(serializer.data, status=status.HTTP_200_OK)


@swagger_auto_schema(
    method="get",
    manual_parameters=[
        openapi.Parameter(
            "video_id",
            openapi.IN_QUERY,
            description=("The ID of the video"),
            type=openapi.TYPE_INTEGER,
            required=True,
        ),
    ],
    responses={200: "Return the video subtitle payload"},
)
@api_view(["GET"])
def list_tasks(request):
    """
    API Endpoint to list the tasks for a video
    Endpoint: /video/list_tasks/
    Method: GET
    """
    # Get the video ID from the request
    if "video_id" in dict(request.query_params):
        video_id = request.query_params["video_id"]
    else:
        return Response(
            {"error": "Please provide a video ID"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Get the video object from the DB
    video = Video.objects.filter(id=video_id).first()

    # Check if the video exists
    if not video:
        return Response(
            {"error": "No video found for the provided ID."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Get the tasks for the video
    tasks = Task.objects.filter(video=video)

    # Return the tasks
    serializer = TaskSerializer(tasks, many=True)
    return Response(serializer.data, status=status.HTTP_200_OK)
