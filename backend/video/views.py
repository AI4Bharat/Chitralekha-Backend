import requests
from drf_yasg import openapi
from rest_framework.decorators import action
from drf_yasg.utils import swagger_auto_schema
from django.http import HttpRequest
from task.models import Task
from task.serializers import TaskSerializer
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.permissions import IsAuthenticatedOrReadOnly
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet
from transcript.models import ORIGINAL_SOURCE, Transcript
from translation.models import Translation
from project.decorators import is_project_owner
from .models import Video, GENDER, MULTISPEAKER_AGE_GROUP
from .serializers import VideoSerializer
from .utils import *
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
from video.tasks import create_videos_async
from organization.models import Organization
from config import *
from collections import Counter
from rest_framework.views import APIView
import config

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
required_fields_project = [
    "Youtube URL",
    "Gender",
    "Source Language",
    "Task Type",
    "Target Language",
    "Assignee",
    "Task Description",
    "Video Description",
]


required_fields_org = [
    "Project Id",
    "Youtube URL",
    "Source Language",
    "Gender",
    "Task Type",
    "Target Language",
    "Assignee",
    "Task Description",
    "Video Description",
    "ETA" 
]


class TransliterationAPIView(APIView):
    def get(self, request, target_language, data, *args, **kwargs):
        json_data = {
            "input": [{"source": data}],
            "config": {
                "language": {
                    "sourceLanguage": "en",
                    "targetLanguage": target_language,
                },
                "isSentence": False,
            },
        }
        logging.info("Calling Transliteration API")
        response_transliteration = requests.post(
            config.transliteration_url,
            headers={"authorization": config.dhruva_key},
            json=json_data,
        )

        transliteration_output = response_transliteration.json()
        if response_transliteration.status_code == 200:
            response = {
                "error": "",
                "input": data,
                "result": transliteration_output["output"][0]["target"],
                "success": True,
            }
        else:
            response = {"error": "", "input": data, "result": [], "success": False}
        return Response(
            response,
            status=status.HTTP_200_OK,
        )


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
        openapi.Parameter(
            "speaker_info",
            openapi.IN_QUERY,
            description=("Speaker's info such as Name, Age, Gender"),
            type=openapi.TYPE_OBJECT,
            required=False,
        ),
        openapi.Parameter(
            "multiple_speaker",
            openapi.IN_QUERY,
            description=(
                "A boolean to determine whether there are multiple or single speakers"
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
    return get_video_func(request)
    # Get the video URL from the query params


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
            "multiple_speaker": openapi.Schema(
                type=openapi.TYPE_BOOLEAN,
                description="Multiple speaker true or false",
            ),
            "speaker_info": openapi.Schema(
                type=openapi.TYPE_OBJECT,
                description="Speaker info of video",
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
    multiple_speaker = request.data.get("multiple_speaker", "false")
    speaker_info = request.data.get("speaker_info")

    multiple_speaker = multiple_speaker.lower() == "true"
    try:
        video = Video.objects.get(id=video_id)
        errors = []

        if description is not None:
            video.description = description

        if gender is not None:
            gender_list = [gender[0] for gender in GENDER]
            if gender.upper() in gender_list:
                video.gender = gender.upper()

        if multiple_speaker is not None:
            video.multiple_speaker = multiple_speaker

        if speaker_info is not None:
            # Get the task transcript status for the video, if none or selected source
            task = (
                Task.objects.filter(video_id=video_id)
                .filter(task_type="TRANSCRIPTION_EDIT")
                .filter(status__in=["SELECTED_SOURCE"])
            )
            if not task:
                errors.append(
                    {
                        "message": f"Video's transcript status must be selected source or none",
                    }
                )

            speaker_info_for_update = []
            gender_list = [gender[0] for gender in GENDER]

            # Find dictionary matching value in list
            dubplicte_ids = find_duplicates(speaker_info, "id")
            if dubplicte_ids:
                errors.append(
                    {
                        "message": f"Ids must be unique Age in : {i}",
                    }
                )

            for i in speaker_info:
                speaker_info_obj = {}

                if i["name"] is not None:
                    speaker_info_obj["name"] = i["name"]

                if i["gender"].upper() in gender_list:
                    speaker_info_obj["gender"] = i["gender"].upper()
                else:
                    errors.append(
                        {
                            "message": f"Invalid Gender in : {i}",
                        }
                    )

                if i["age"] in MULTISPEAKER_AGE_GROUP:
                    speaker_info_obj["age"] = i["age"]
                else:
                    errors.append(
                        {
                            "message": f"Invalid Age in : {i}",
                        }
                    )

                if i["id"] is not None:
                    speaker_info_obj["id"] = i["id"]

                speaker_info_for_update.append(speaker_info_obj)

            video.speaker_info = speaker_info_for_update

        if len(errors) > 0:
            return Response(
                {"message": "Invalid Data", "response": errors},
                status=status.HTTP_400_BAD_REQUEST,
            )
        else:
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

    if not request.FILES["csv"] or not request.FILES["csv"].name.endswith(".csv"):
        return Response(
            {"message": "No CSV file uploaded"}, status=status.HTTP_400_BAD_REQUEST
        )
    csv_file = request.FILES["csv"]
    decoded_file = csv_file.read().decode("utf-8").splitlines()
    csv_reader = csv.DictReader(decoded_file)
    if not set(required_fields_project).issubset(csv_reader.fieldnames):
        return Response(
            {
                "message": f"Missing columns: {', '.join(set(required_fields_project) - set(csv_reader.fieldnames))}"
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
        if not isinstance(row["Gender"], str) or row["Gender"].lower() not in [
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
            valid_row["gender"] = mapped_gender[row["Gender"].lower()]
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
            valid_row["assignee"] = User.objects.get(email=row["Assignee"]).id

        valid_row["task_description"] = row["Task Description"]
        valid_row["video_description"] = row["Video Description"]
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
        return Response(
            {"message": "CSV uploaded successfully"}, status=status.HTTP_200_OK
        )


def call_async_video(user_id, valid_rows, existing_videos, project_id):
    create_videos_async.delay(user_id, valid_rows, existing_videos, project_id)


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

    try:
        tasks_list = []
        params = {
            "state": "RECEIVED",
            "sort_by": "received",
            "name": "task.tasks.celery_asr_call",
        }
        url = f"{flower_url}/api/tasks"
        if flower_username and flower_password:
            res = requests.get(
                url, params=params, auth=(flower_username, flower_password)
            )
        else:
            res = requests.get(url, params=params)
        data = res.json()
        task_data = list(data.values())
        for elem in task_data:
            tasks_list.append(eval(elem["kwargs"])["task_id"])
        if len(data) > 29:
            return Response(
                {
                    "message": "There are {} Transcription calls in the queue already. Please wait, till these are completed.".format(
                        len(data)
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
    except:
        logging.info("There was an issue in checking ASR queue.")

    decrypted = base64.b64decode(csv_content).decode("utf-8")
    csv_data = []
    with io.StringIO(decrypted) as fp:
        reader = csv.reader(fp, delimiter=",", quotechar='"')
        for row in reader:
            new_row = ",".join(row)
            csv_data.append(new_row)

    if len(csv_data) > 30:
        return Response(
            {"message": "Number of rows is greater than 30."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    try:
        csv_reader = csv.DictReader(csv_data)
    except:
        return Response(
            {"message": "Error in reading CSV file."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if not set(required_fields_project).issubset(csv_reader.fieldnames):
        return Response(
            {
                "message": f"Missing columns: {', '.join(set(required_fields_project) - set(csv_reader.fieldnames))}"
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
                    "message": f"Invalid source language: {row['Source Language']}",
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
                else:
                    valid_row["target_language"] = row["Target Language"]
            valid_row["task_type"] = mapped_task_type[row["Task Type"].lower()]

        if not isinstance(row["Gender"], str) or row["Gender"].lower() not in [
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
            valid_row["gender"] = mapped_gender[row["Gender"].lower()]
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
        elif len(row["Target Language"]) == 0:
            valid_row["target_language"] = None
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
            valid_row["assignee"] = User.objects.get(email=row["Assignee"]).id

        valid_row["video_description"] = row["Video Description"]
        valid_row["task_description"] = row["Task Description"]
        video = Video.objects.filter(url=row["Youtube URL"]).first()
        existing_videos = []
        if len(errors) == 0:
            if video is not None:
                if video.project_id.id != project.id:
                    errors.append(
                        {
                            "row_no": f"Row {row_num}",
                            "message": f"Video {row['Youtube URL']} exists in another Project: {video.project_id.title}",
                        }
                    )
                else:
                    existing_videos.append({"video": video.id, "row": valid_row})
                    valid_rows.append(valid_row)
            else:
                valid_rows.append(valid_row)

    if len(errors) > 0:
        return Response(
            {"message": "Invalid CSV", "response": errors},
            status=status.HTTP_400_BAD_REQUEST,
        )
    else:
        call_async_video(request.user.id, valid_rows, existing_videos, project_id)
        return Response(
            {"message": "CSV uploaded successfully"}, status=status.HTTP_200_OK
        )


@swagger_auto_schema(
    method="post",
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        required=["csv", "org_id"],
        properties={
            "org_id": openapi.Schema(
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
def upload_csv_org(request):
    """
    API Endpoint to upload a csv file
    Endpoint: /video/upload_csv/
    Method: POST
    """

    logging.info("Calling Upload API for Org...")
    org_id = request.data.get("org_id")
    csv_content = request.data.get("csv")

    try:
        org = Organization.objects.get(pk=org_id)
    except Organization.DoesNotExist:
        return Response(
            {"message": "Organization not found"}, status=status.HTTP_404_NOT_FOUND
        )

    if org.organization_owner.id != request.user.id:
        return Response(
            {"message": "You are not allowed to upload CSV."},
            status=status.HTTP_403_FORBIDDEN,
        )

    try:
        tasks_list = []
        params = {
            "state": "RECEIVED",
            "sort_by": "received",
            "name": "task.tasks.celery_asr_call",
        }
        url = f"{flower_url}/api/tasks"
        if flower_username and flower_password:
            res = requests.get(
                url, params=params, auth=(flower_username, flower_password)
            )
        else:
            res = requests.get(url, params=params)
        data = res.json()
        task_data = list(data.values())
        for elem in task_data:
            tasks_list.append(eval(elem["kwargs"])["task_id"])
        if len(data) > 29:
            return Response(
                {
                    "message": "There are {} Transcription calls in the queue already. Please wait, till these are completed.".format(
                        len(data)
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
    except:
        logging.info("There was an issue in checking ASR queue.")

    if not org.enable_upload:
        return Response(
            {"message": "CSV upload is not enabled. Please contact the administrator!"},
            status=status.HTTP_403_FORBIDDEN,
        )

    decrypted = base64.b64decode(csv_content).decode("utf-8")
    csv_data = []
    with io.StringIO(decrypted) as fp:
        reader = csv.reader(fp, delimiter=",", quotechar='"')
        for row in reader:
            new_row = ",".join(row)
            csv_data.append(new_row)

    if len(csv_data) > 200:
        return Response(
            {"message": "Number of rows is greater than 200."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    all_task_types = []

    csv_reader_1 = csv.DictReader(csv_data)
    for task in csv_reader_1:
        all_task_types.append(task["Task Type"].lower())
    # Count the occurrences of each unique string
    string_counts = Counter(all_task_types)
    # Display the results
    asr_tts_tasks = (
        string_counts["transcription edit"] + string_counts["voiceover edit"]
    )
    logging.info("Sum of Transcription and VO tasks is %s", str(asr_tts_tasks))
    if asr_tts_tasks > 50:
        return Response(
            {
                "message": "Sum of Transcription and VoiceOver in a CSV can't be more than 50."
            },
            status=status.HTTP_400_BAD_REQUEST,
        )
    csv_reader = csv.DictReader(csv_data)
    if not set(required_fields_org).issubset(csv_reader.fieldnames):
        return Response(
            {
                "message": f"Missing columns: {', '.join(set(required_fields_org) - set(csv_reader.fieldnames))}"
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    if csv_reader.fieldnames != required_fields_org:
        return Response(
            {"message": "The sequence of fields given in CSV is wrong."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    errors = []
    print(csv_reader.fieldnames)
    row_num = 0

    valid_rows = []
    existing_videos = []

    for row in csv_reader:
        valid_row = {}
        row_num += 1
        if not isinstance(int(row["Project Id"]), int):
            errors.append(
                {
                    "row_no": f"Row {row_num}",
                    "message": f"Invalid Project Id: {row['Project Id']}",
                }
            )
            continue
        else:
            project_id = row["Project Id"]
            try:
                project = Project.objects.get(pk=project_id)
                if project.organization_id != org:
                    errors.append(
                        {
                            "row_no": f"Row {row_num}",
                            "message": f"Project Id does not belong to this organization: {row['Project Id']}",
                        }
                    )
                    continue
                valid_row["project_id"] = project_id
            except Project.DoesNotExist:
                errors.append(
                    {
                        "row_no": f"Row {row_num}",
                        "message": f"Project Id does not exist: {row['Project Id']}",
                    }
                )
                continue
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
                    "message": f"Invalid source language: {row['Source Language']}",
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
                else:
                    valid_row["target_language"] = row["Target Language"]
            valid_row["task_type"] = mapped_task_type[row["Task Type"].lower()]

        if not isinstance(row["Gender"], str) or row["Gender"].lower() not in [
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
            valid_row["gender"] = mapped_gender[row["Gender"].lower()]
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
        elif len(row["Target Language"]) == 0:
            valid_row["target_language"] = None
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
            valid_row["assignee"] = User.objects.get(email=row["Assignee"]).id

        #ETA Validation
        format = "%d-%m-%Y"
        input_eta=datetime.datetime.strptime(row["ETA"], format)
        curr_date=datetime.datetime.now().date()
        #DD-MM-YYYY eta format check
        if (
            bool(input_eta)==False
        ):
            errors.append(
                {
                    "row_no": f"Row {row_num}",
                    "message": f"Invalid ETA Format, expected format is dd-mm-yyyy: received{row['ETA']}",
                }
            )
        #Verify ETA >= currDate 
        elif (input_eta.date() < curr_date):
            errors.append(
                {
                    "row_no": f"Row {row_num}",
                    "message": f"ETA can't be less than current Date: received{row['ETA']}",
                }
            )

        else:
            #Convert ETA format to 2023-09-22T18:30:00.000Z
            valid_row["ETA"] = input_eta.strftime("%Y-%m-%dT18:29:00.000Z")


        valid_row["task_description"] = row["Task Description"]
        valid_row["video_description"] = row["Video Description"]
        video = Video.objects.filter(url=row["Youtube URL"]).first()
        if len(errors) == 0:
            if video is not None:
                if video.project_id.id != project.id:
                    errors.append(
                        {
                            "row_no": f"Row {row_num}",
                            "message": f"Video {row['Youtube URL']} exists in another Project: {video.project_id.title}",
                        }
                    )
                else:
                    existing_videos.append({"video": video.id, "row": valid_row})
                    valid_rows.append(valid_row)
            else:
                valid_rows.append(valid_row)
    if len(errors) > 0:
        return Response(
            {"message": "Invalid CSV", "response": errors},
            status=status.HTTP_400_BAD_REQUEST,
        )
    else:
        call_async_video(request.user.id, valid_rows, existing_videos, project_id)
        return Response(
            {"message": "CSV uploaded successfully"}, status=status.HTTP_200_OK
        )
