import urllib
import requests
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
from .models import Video, GENDER
from task.views import TaskViewSet
from task.serializers import TaskStatusSerializer
from .serializers import VideoSerializer
from .utils import (
    get_data_from_google_video,
    get_subtitles_from_google_video,
    drive_info_extractor,
    DownloadError,
    get_export_transcript,
    get_export_translation,
)
from django.utils import timezone
from django.http import HttpResponse
import io
import zipfile
from project.models import Project
import logging
import datetime
from datetime import timedelta
import csv
import re
from rest_framework.decorators import parser_classes
from rest_framework.parsers import MultiPartParser, FormParser
from users.models import User
import base64
import io
import csv


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
        openapi.Parameter(
            "create",
            openapi.IN_QUERY,
            description=("A boolean to pass to determine get or create"),
            type=openapi.TYPE_BOOLEAN,
            required=False,
        ),
        openapi.Parameter(
            "gender",
            openapi.IN_QUERY,
            description=("Gender of video's voice"),
            type=openapi.TYPE_STRING,
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
    create = request.query_params.get("create", "false")
    gender = request.query_params.get("gender", "MALE")

    create = create.lower() == "true"
    if create:
        video = Video.objects.filter(url=url).first()
        if video is not None:
            return Response(
                {
                    "message": "Video is already a part of project -> {}.".format(
                        video.project_id.title
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
    # Convert audio only to boolean
    is_audio_only = is_audio_only.lower() == "true"
    if not url:
        return Response(
            {"message": "Video URL not provided in query params."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if gender is not None:
        gender_list = [gender[0] for gender in GENDER]
        if gender.upper() in gender_list:
            gender = gender.upper()
        else:
            gender = "MALE"

    project = Project.objects.filter(pk=project_id).first()
    if project is None:
        return Response(
            {"message": "Project is not found. "},
            status=status.HTTP_404_NOT_FOUND,
        )

    organization = project.organization_id
    default_task_eta = project.default_eta
    default_task_priority = project.default_priority
    default_task_description = project.default_description
    consolidated_report = []
    detailed_report = []
    message = ""
    fail_count = 0
    success_count = 0
    ## PATCH: Handle audio_only files separately for google drive links
    ## TODO: Move it to an util function
    if "drive.google.com" in url and is_audio_only:

        # Construct a direct download link from the google drive url
        # get the id from the drive link
        try:
            file_id = drive_info_extractor._match_id(url)
        except Exception:
            return Response(
                {"message": "Invalid Google Drive URL."},
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
                "gender": gender,
            },
        )
        serializer = VideoSerializer(video)
        response_data = {
            "video": serializer.data,
        }

        if is_audio_only:
            response_data["direct_audio_url"] = direct_audio_url
        else:
            response_data["direct_video_url"] = direct_video_url

        if created:
            video.save()
            logging.info("Video is created.")
            default_task_types = (
                project.default_task_types or organization.default_task_types
            )
            default_target_languages = (
                project.default_target_languages
                or organization.default_target_languages
            )

            if default_task_types is not None:
                for task_type in default_task_types:
                    if (
                        default_target_languages is not None
                        and "TRANSCRIPTION" not in task_type
                    ):
                        for target_language in default_target_languages:
                            task_response = create_tasks(
                                video.id,
                                task_type,
                                request.user,
                                default_task_eta,
                                default_task_priority,
                                default_task_description,
                                target_language,
                            )
                            detailed_report.extend(
                                task_response["response"]["detailed_report"]
                            )
                            if (
                                task_response["response"]["detailed_report"][0][
                                    "status"
                                ]
                                == "Fail"
                            ):
                                fail_count += 1
                            else:
                                success_count += 1
                    else:
                        task_response = create_tasks(
                            video.id,
                            task_type,
                            request.user,
                            default_task_eta,
                            default_task_priority,
                            default_task_description,
                        )
                        detailed_report.extend(
                            task_response["response"]["detailed_report"]
                        )
                        if (
                            task_response["response"]["detailed_report"][0]["status"]
                            == "Fail"
                        ):
                            fail_count += 1
                        else:
                            success_count += 1
                if fail_count > 0:
                    message = "{0} Tasks creation failed.".format(fail_count)
                    consolidated_report.append(
                        {"message": "Tasks creation failed.", "count": fail_count}
                    )
                if success_count > 0:
                    message = (
                        "{0} Tasks created successfully.".format(success_count)
                        + message
                    )
                    consolidated_report.append(
                        {
                            "message": "Tasks created successfully.",
                            "count": success_count,
                        }
                    )
            response_data["consolidated_report"] = consolidated_report
            response_data["detailed_report"] = detailed_report
            response_data["message"] = "Video created successfully." + message

            return Response(
                response_data,
                status=status.HTTP_200_OK,
            )
        else:
            return Response(
                response_data,
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
            {"message": "This is an invalid video URL."},
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
            "gender": gender,
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
        default_task_types = (
            project.default_task_types or organization.default_task_types
        )
        default_target_languages = (
            project.default_target_languages or organization.default_target_languages
        )

        if default_task_types is not None:
            for task_type in default_task_types:
                if (
                    default_target_languages is not None
                    and "TRANSCRIPTION" not in task_type
                ):
                    for target_language in default_target_languages:
                        task_response = create_tasks(
                            video.id,
                            task_type,
                            request.user,
                            default_task_eta,
                            default_task_priority,
                            default_task_description,
                            target_language,
                        )
                        detailed_report.extend(
                            task_response["response"]["detailed_report"]
                        )
                        if (
                            task_response["response"]["detailed_report"][0]["status"]
                            == "Fail"
                        ):
                            fail_count += 1
                        else:
                            success_count += 1
                else:
                    task_response = create_tasks(
                        video.id,
                        task_type,
                        request.user,
                        default_task_eta,
                        default_task_priority,
                        default_task_description,
                    )
                    detailed_report.extend(task_response["response"]["detailed_report"])

                    if (
                        task_response["response"]["detailed_report"][0]["status"]
                        == "Fail"
                    ):
                        fail_count += 1
                    else:
                        success_count += 1

            if fail_count > 0:
                message = "{0} Tasks creation failed.".format(fail_count)
                consolidated_report.append(
                    {"message": "Tasks creation failed.", "count": fail_count}
                )
            if success_count > 0:
                message = (
                    "{0} Tasks created successfully.".format(success_count) + message
                )
                consolidated_report.append(
                    {"message": "Tasks created successfully.", "count": success_count}
                )
            response_data["consolidated_report"] = consolidated_report
            response_data["detailed_report"] = detailed_report

        response_data["message"] = "Video created successfully." + message
        return Response(
            response_data,
            status=status.HTTP_200_OK,
        )
    else:
        return Response(
            response_data,
            status=status.HTTP_200_OK,
        )


def create_tasks(
    video_id, task_type, user, eta, priority, description, target_language=None
):
    data = TaskViewSet(detail=True)
    new_request = HttpRequest()
    new_request.user = user
    new_request.data = {
        "task_type": task_type,
        "video_ids": [video_id],
        "target_language": target_language,
        "eta": eta,
        "priority": priority,
        "description": description,
    }
    logging.info("Creation of task started for %s", task_type)
    ret = data.create(new_request)
    return ret.data


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
            {"message": "Please provide a video ID"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Get the video object from the DB
    video = Video.objects.filter(id=video_id).first()

    # Check if the video exists
    if not video:
        return Response(
            {"message": "No video found for the provided ID."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Get the tasks for the video
    tasks = Task.objects.filter(video=video)

    # Return the tasks
    serializer = TaskSerializer(tasks, many=True)
    return Response(serializer.data, status=status.HTTP_200_OK)


@swagger_auto_schema(
    method="get",
    manual_parameters=[
        openapi.Parameter(
            "video_id",
            openapi.IN_QUERY,
            description=("An integer to pass the video id"),
            type=openapi.TYPE_INTEGER,
            required=True,
        ),
        openapi.Parameter(
            "export_type",
            openapi.IN_QUERY,
            description=("export type parameter srt/vtt/txt/docx"),
            type=openapi.TYPE_STRING,
            required=True,
        ),
    ],
    responses={200: "Transcript is exported"},
)
@api_view(["GET"])
def download_all(request):
    """
    API Endpoint to download all the completed transcripts/translations for a video
    Endpoint: /video/download_all/
    Method: GET
    """
    video_id = request.query_params.get("video_id")
    export_type = request.query_params.get("export_type")
    if video_id is None or export_type is None:
        return Response(
            {"message": "missing required params: video_id or export_type"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        video = Video.objects.get(id=video_id)
    except Video.DoesNotExist:
        return Response(
            {"message": "Video not found"}, status=status.HTTP_404_NOT_FOUND
        )

    tasks = Task.objects.filter(video=video).all()
    if tasks.filter(task_type="TRANSCRIPTION_REVIEW").exists():
        transcript_task = (
            tasks.filter(task_type="TRANSCRIPTION_REVIEW")
            .filter(status="COMPLETE")
            .first()
        )
    elif (
        tasks.filter(task_type="TRANSCRIPTION_EDIT").filter(status="COMPLETE").exists()
    ):
        transcript_task = (
            tasks.filter(task_type="TRANSCRIPTION_EDIT")
            .filter(status="COMPLETE")
            .first()
        )
    else:
        transcript_task = None

    languages_in_review_tasks = None
    translation_tasks = []
    if export_type != "ytt":
        if tasks.filter(task_type="TRANSLATION_REVIEW").exists():
            for translation_task in tasks.filter(task_type="TRANSLATION_REVIEW").filter(
                status="COMPLETE"
            ):
                translation_tasks.append(translation_task)
            languages_in_review_tasks = tasks.filter(
                task_type="TRANSLATION_REVIEW"
            ).values_list("target_language", flat=True)
        if (
            tasks.filter(task_type="TRANSLATION_EDIT")
            .filter(status="COMPLETE")
            .exists()
        ):
            edit_translation_tasks = tasks.filter(task_type="TRANSLATION_EDIT").filter(
                status="COMPLETE"
            )
            languages_in_edited_tasks = edit_translation_tasks.values_list(
                "target_language", flat=True
            )
            if languages_in_review_tasks != None:
                languages_in_edit_tasks_and_not_in_reivew_tasks = list(
                    set(languages_in_edited_tasks) - set(languages_in_review_tasks)
                )
                for translation_task in edit_translation_tasks.filter(
                    target_language__in=languages_in_edit_tasks_and_not_in_reivew_tasks
                ):
                    translation_tasks.append(translation_task)
            else:
                for translation_task in edit_translation_tasks:
                    translation_tasks.append(translation_task)

    if transcript_task is None and len(translation_tasks) == 0:
        return Response(
            {
                "message": "No Completed transcripts/translations found to be downloaded."
            },
            status=status.HTTP_404_NOT_FOUND,
        )

    time_now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    zip_file = io.BytesIO()
    with zipfile.ZipFile(zip_file, "w") as zf:
        if transcript_task is not None:
            transcript = get_export_transcript(request, transcript_task.id, export_type)
            zf.writestr(
                f"{transcript_task.video.name}_{time_now}.{export_type}",
                transcript.content,
            )

        if translation_tasks is not None:
            for translation_task in translation_tasks:
                translation = get_export_translation(
                    request, translation_task.id, export_type
                )
                zf.writestr(
                    f"{transcript_task.video.name}_{time_now}_{translation_task.target_language}.{export_type}",
                    translation.content,
                )
    zip_file.seek(0)
    response = HttpResponse(
        zip_file, content_type="application/zip", status=status.HTTP_200_OK
    )
    response[
        "Content-Disposition"
    ] = f"attachment; filename=Chitralekha_{time_now}_all.zip"
    return response


@swagger_auto_schema(
    method="patch",
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        properties={
            "video_id": openapi.Schema(type=openapi.TYPE_INTEGER),
            "description": openapi.Schema(
                type=openapi.TYPE_STRING,
                description="Description of video",
            ),
            "gender": openapi.Schema(
                type=openapi.TYPE_STRING,
                description="Gender of video's voice",
            ),
        },
        required=["video_id"],
    ),
    responses={200: "Video's information is updated"},
)
@api_view(["PATCH"])
def update_video(request):
    """
    API Endpoint to update parameter of video
    Endpoint: /video/update_video/
    Method: PATCH
    """
    video_id = request.data.get("video_id")
    description = request.data.get("description")
    gender = request.data.get("gender")

    try:
        video = Video.objects.get(id=video_id)

        if description is not None:
            video.description = description

        if gender is not None:
            gender_list = [gender[0] for gender in GENDER]
            if gender.upper() in gender_list:
                video.gender = gender.upper()

        video.save()

        return Response(
            {
                "message": "Video updated successfully.",
            },
            status=status.HTTP_200_OK,
        )
    except Video.DoesNotExist:
        return Response(
            {"message": "Video not found"}, status=status.HTTP_404_NOT_FOUND
        )


def create_video(
    request, url, project_id, description, gender, assignee=None, lang="en"
):
    new_request = HttpRequest()
    new_request.method = "GET"
    new_request.user = request.user
    new_request.GET = request.GET.copy()
    new_request.GET["multimedia_url"] = url
    new_request.GET["lang"] = lang
    new_request.GET["project_id"] = project_id
    new_request.GET["description"] = description
    new_request.GET["is_audio_only"] = "true"
    new_request.GET["create"] = "true"
    new_request.GET["gender"] = gender
    new_request.GET["assignee"] = assignee
    # return get_video(new_request)


@swagger_auto_schema(
    method="post",
    manual_parameters=[
        openapi.Parameter(
            name="csv",
            in_=openapi.IN_FORM,
            type=openapi.TYPE_FILE,
            required=True,
            description="CSV File to upload",
        ),
        openapi.Parameter(
            "project_id",
            openapi.IN_QUERY,
            description=("Id of the project to which this video belongs"),
            type=openapi.TYPE_INTEGER,
            required=True,
        ),
    ],
    responses={200: "CSV uploaded successfully"},
)
@api_view(["POST"])
@parser_classes([MultiPartParser, FormParser])
def upload_csv(request):
    """
    API Endpoint to upload a csv file
    Endpoint: /video/upload_csv/
    Method: POST
    """

    logging.info("Calling Upload API...")
    project_id = request.query_params.get("project_id")
    accepted_languages = [
        "as",
        "bn",
        "en",
        "gu",
        "hi",
        "kn",
        "ml",
        "mr",
        "or",
        "pa",
        "ta",
        "te",
    ]
    accepted_task_types = [
        "transcription edit",
        "transcription review",
        "translation edit",
        "translation review",
        "voiceover edit",
    ]
    mapped_task_type = {
        "transcription edit": "TRANSCRIPTION_EDIT",
        "transcription review": "TRANSCRIPTION_REVIEW",
        "translation edit": "TRANSLATION_EDIT",
        "translation review": "TRANSLATION_REVIEW",
        "voiceover edit": "VOICEOVER_EDIT",
    }
    mapped_gender = {"male": "Male", "female": "Female"}
    required_fields = [
        "Youtube URL",
        "Speaker",
        "Source Language",
        "Task Type",
        "Target Language",
        "Assignee",
        "Description",
    ]
    organization = request.user.organization
    if not request.FILES["csv"] or not request.FILES["csv"].name.endswith(".csv"):
        return Response(
            {"message": "No CSV file uploaded"}, status=status.HTTP_400_BAD_REQUEST
        )
    csv_file = request.FILES["csv"]
    decoded_file = csv_file.read().decode("utf-8").splitlines()
    csv_reader = csv.DictReader(decoded_file)
    if not set(required_fields).issubset(csv_reader.fieldnames):
        return Response(
            {
                "message": f"Missing columns: {', '.join(set(required_fields) - set(csv_reader.fieldnames))}"
            },
            status=status.HTTP_400_BAD_REQUEST,
        )
    errors = []
    print(csv_reader.fieldnames)
    row_num = 0
    try:
        project = Project.objects.get(pk=project_id)

    except Project.DoesNotExist:
        return Response(
            {"message": "Project not found"}, status=status.HTTP_404_NOT_FOUND
        )
    valid_rows = []
    for row in csv_reader:
        valid_row = {}
        row_num += 1
        if not isinstance(row["Youtube URL"], str) or not re.match(
            r"^(https?\:\/\/)?(www\.youtube\.com|youtu\.?be)\/.+", row["Youtube URL"]
        ):
            errors.append(
                {
                    "row_no": f"Row {row_num}",
                    "message": f"Invalid YouTube URL: {row['Youtube URL']}",
                }
            )
        else:
            valid_row["url"] = row["Youtube URL"]
        if (
            not isinstance(row["Source Language"], str)
            or row["Source Language"] not in accepted_languages
        ):
            errors.append(
                {
                    "row_no": f"Row {row_num}",
                    "message": f"Invalid language: {row['Source Language']}",
                }
            )
        else:
            valid_row["lang"] = row["Source Language"]
        if (
            not isinstance(row["Task Type"], str)
            or row["Task Type"].lower() not in accepted_task_types
        ):
            errors.append(
                {
                    "row_no": f"Row {row_num}",
                    "message": f"Invalid task type: {row['Task Type']}",
                }
            )
        else:
            if (
                "translation" in row["Task Type"].lower()
                or "voiceover" in row["Task Type"].lower()
            ):
                if row["Target Language"] not in accepted_languages:
                    errors.append(
                        {
                            "row_no": f"Row {row_num}",
                            "message": f"Empty or Invalid target language: {row['Target Language']}",
                        }
                    )
        if not isinstance(row["Speaker"], str) or row["Speaker"].lower() not in [
            "male",
            "female",
        ]:
            errors.append(
                {
                    "row_no": f"Row {row_num}",
                    "message": f"Invalid gender: {row['Speaker']}",
                }
            )
        else:
            valid_row["gender"] = mapped_gender[row["Speaker"].lower()]
        if (
            not isinstance(row["Target Language"], str)
            and row["Target Language"] not in accepted_languages
            and "translation" not in row["Task Type"].lower()
            and "voiceover" not in row["Task Type"].lower()
        ):
            errors.append(
                {
                    "row_no": f"Row {row_num}",
                    "message": f"Invalid target language: {row['Target Language']}",
                }
            )
        else:
            valid_row["target_language"] = row["Target Language"]
        if row["Assignee"] not in project.members.all().values_list("email", flat=True):
            if row["Assignee"] is None or len(row["Assignee"]) == 0:
                valid_row["assignee"] = None
            else:
                errors.append(
                    {
                        "row_no": f"Row {row_num}",
                        "message": f"Invalid Assignee: {row['Assignee']}",
                    }
                )
        else:
            valid_row["assignee"] = User.objects.get(email=row["Assignee"])

        valid_row["description"] = row["Description"]
        video = Video.objects.filter(url=row["Youtube URL"]).first()
        existing_videos = []
        if video is not None:
            if video.project_id.id != project.id:
                errors.append(
                    {
                        "row_no": f"Row {row_num}",
                        "message": f"Video {row['Youtube URL']} exists in another Project: {video.project_id.title}",
                    }
                )
            else:
                existing_videos.append(video)
        if len(errors) == 0:
            valid_rows.append(valid_row)
    if len(errors) > 0:
        return Response(
            {"message": "Invalid CSV", "response": errors},
            status=status.HTTP_400_BAD_REQUEST,
        )
    else:
        """
        for row in valid_rows:
            create_video(
                request,
                row["url"],
                project.id,
                existing_videos,
                row["description"],
                row["gender"],
                row["assignee"],
                row["lang"],
            )
        """
        return Response(
            {"message": "CSV uploaded successfully"}, status=status.HTTP_200_OK
        )


@swagger_auto_schema(
    method="post",
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        required=["csv", "project_id"],
        properties={
            "project_id": openapi.Schema(
                type=openapi.TYPE_INTEGER,
                description="An integer identifying the project instance",
            ),
            "csv": openapi.Schema(
                type=openapi.TYPE_STRING,
                description="A string to pass the csv data",
            ),
        },
    ),
    responses={
        200: "CSV uploaded successfully",
    },
)
@api_view(["POST"])
def upload_csv_data(request):
    """
    API Endpoint to upload a csv file
    Endpoint: /video/upload_csv/
    Method: POST
    """

    logging.info("Calling Upload API...")
    project_id = request.data.get("project_id")
    csv_content = request.data.get("csv")

    accepted_languages = [
        "as",
        "bn",
        "en",
        "gu",
        "hi",
        "kn",
        "ml",
        "mr",
        "or",
        "pa",
        "ta",
        "te",
    ]
    accepted_task_types = [
        "transcription edit",
        "transcription review",
        "translation edit",
        "translation review",
        "voiceover edit",
    ]
    mapped_task_type = {
        "transcription edit": "TRANSCRIPTION_EDIT",
        "transcription review": "TRANSCRIPTION_REVIEW",
        "translation edit": "TRANSLATION_EDIT",
        "translation review": "TRANSLATION_REVIEW",
        "voiceover edit": "VOICEOVER_EDIT",
    }
    mapped_gender = {"male": "Male", "female": "Female"}
    required_fields = [
        "Youtube URL",
        "Speaker",
        "Source Language",
        "Task Type",
        "Target Language",
        "Assignee",
        "Description",
    ]

    decrypted = base64.b64decode(csv_content).decode("utf-8")
    csv_data = []
    with io.StringIO(decrypted) as fp:
        reader = csv.reader(fp, delimiter=",", quotechar='"')
        for row in reader:
            new_row = ",".join(row)
            csv_data.append(new_row)
    csv_reader = csv.DictReader(csv_data)
    if not set(required_fields).issubset(csv_reader.fieldnames):
        return Response(
            {
                "message": f"Missing columns: {', '.join(set(required_fields) - set(csv_reader.fieldnames))}"
            },
            status=status.HTTP_400_BAD_REQUEST,
        )
    errors = []
    print(csv_reader.fieldnames)
    row_num = 0
    try:
        project = Project.objects.get(pk=project_id)

    except Project.DoesNotExist:
        return Response(
            {"message": "Project not found"}, status=status.HTTP_404_NOT_FOUND
        )
    valid_rows = []
    for row in csv_reader:
        valid_row = {}
        row_num += 1
        if not isinstance(row["Youtube URL"], str) or not re.match(
            r"^(https?\:\/\/)?(www\.youtube\.com|youtu\.?be)\/.+", row["Youtube URL"]
        ):
            errors.append(
                {
                    "row_no": f"Row {row_num}",
                    "message": f"Invalid YouTube URL: {row['Youtube URL']}",
                }
            )
        else:
            valid_row["url"] = row["Youtube URL"]
        if (
            not isinstance(row["Source Language"], str)
            or row["Source Language"] not in accepted_languages
        ):
            errors.append(
                {
                    "row_no": f"Row {row_num}",
                    "message": f"Invalid language: {row['Source Language']}",
                }
            )
        else:
            valid_row["lang"] = row["Source Language"]
        if (
            not isinstance(row["Task Type"], str)
            or row["Task Type"].lower() not in accepted_task_types
        ):
            errors.append(
                {
                    "row_no": f"Row {row_num}",
                    "message": f"Invalid task type: {row['Task Type']}",
                }
            )
        else:
            if (
                "translation" in row["Task Type"].lower()
                or "voiceover" in row["Task Type"].lower()
            ):
                if row["Target Language"] not in accepted_languages:
                    errors.append(
                        {
                            "row_no": f"Row {row_num}",
                            "message": f"Empty or Invalid target language: {row['Target Language']}",
                        }
                    )
        if not isinstance(row["Speaker"], str) or row["Speaker"].lower() not in [
            "male",
            "female",
        ]:
            errors.append(
                {
                    "row_no": f"Row {row_num}",
                    "message": f"Invalid gender: {row['Speaker']}",
                }
            )
        else:
            valid_row["gender"] = mapped_gender[row["Speaker"].lower()]
        if (
            not isinstance(row["Target Language"], str)
            and row["Target Language"] not in accepted_languages
            and "translation" not in row["Task Type"].lower()
            and "voiceover" not in row["Task Type"].lower()
        ):
            errors.append(
                {
                    "row_no": f"Row {row_num}",
                    "message": f"Invalid target language: {row['Target Language']}",
                }
            )
        else:
            valid_row["target_language"] = row["Target Language"]

        if row["Assignee"] not in project.members.all().values_list("email", flat=True):
            if row["Assignee"] is None or len(row["Assignee"]) == 0:
                valid_row["assignee"] = None
            else:
                errors.append(
                    {
                        "row_no": f"Row {row_num}",
                        "message": f"Invalid Assignee: {row['Assignee']}",
                    }
                )
        else:
            valid_row["assignee"] = User.objects.get(email=row["Assignee"])

        valid_row["description"] = row["Description"]
        video = Video.objects.filter(url=row["Youtube URL"]).first()
        existing_videos = []
        if video is not None:
            if video.project_id.id != project.id:
                errors.append(
                    {
                        "row_no": f"Row {row_num}",
                        "message": f"Video {row['Youtube URL']} exists in another Project: {video.project_id.title}",
                    }
                )
            else:
                existing_videos.append(video)
        if len(errors) == 0:
            valid_rows.append(valid_row)
    if len(errors) > 0:
        return Response(
            {"message": "Invalid CSV", "response": errors},
            status=status.HTTP_400_BAD_REQUEST,
        )
    else:
        """
        for row in valid_rows:
            create_video(
                request,
                row["url"],
                project.id,
                existing_videos,
                row["description"],
                row["gender"],
                row["assignee"],
                row["lang"],
            )
        """
        return Response(
            {"message": "CSV uploaded successfully"}, status=status.HTTP_200_OK
        )
