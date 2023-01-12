from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet
from video.models import Video
from task.models import Task
from rest_framework.decorators import action
from django.http import HttpResponse
from django.core.files.base import ContentFile
import requests
from json_to_ytt import *
from translation.models import Translation
from project.models import Project
from organization.models import Organization
from translation.utils import (
    get_batch_translations_using_indictrans_nmt_api,
    generate_translation_payload,
    translation_mg,
)


from .models import (
    Transcript,
    TRANSCRIPT_TYPE,
    ORIGINAL_SOURCE,
    UPDATED_ORIGINAL_SOURCE,
    MACHINE_GENERATED,
    UPDATED_MACHINE_GENERATED,
    MANUALLY_CREATED,
    UPDATED_MANUALLY_CREATED,
    TRANSCRIPTION_SELECT_SOURCE,
    TRANSCRIPTION_EDITOR_ASSIGNED,
    TRANSCRIPTION_EDIT_INPROGRESS,
    TRANSCRIPTION_EDIT_COMPLETE,
    TRANSCRIPTION_REVIEWER_ASSIGNED,
    TRANSCRIPTION_REVIEW_INPROGRESS,
    TRANSCRIPTION_REVIEW_COMPLETE,
)

from .decorators import is_transcript_editor
from .serializers import TranscriptSerializer
from .utils.asr import get_asr_supported_languages, make_asr_api_call
from users.models import User
from rest_framework.response import Response
from functools import wraps
from rest_framework import status


@swagger_auto_schema(
    method="get",
    manual_parameters=[
        openapi.Parameter(
            "task_id",
            openapi.IN_QUERY,
            description=("An integer to pass the video id"),
            type=openapi.TYPE_INTEGER,
            required=True,
        ),
        openapi.Parameter(
            "export_type",
            openapi.IN_QUERY,
            description=("export type parameter srt/vtt/txt/ytt"),
            type=openapi.TYPE_STRING,
            required=True,
        ),
    ],
    responses={200: "Transcript is exported"},
)
@api_view(["GET"])
def export_transcript(request):
    task_id = request.query_params.get("task_id")
    export_type = request.query_params.get("export_type")

    if task_id is None or export_type is None:
        return Response(
            {"message": "missing param : task_id or export_type"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    supported_types = ["srt", "vtt", "txt", "ytt"]
    if export_type not in supported_types:
        return Response(
            {
                "message": "exported type only supported formats are : {srt, vtt, txt, ytt} "
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        task = Task.objects.get(pk=task_id)
    except Task.DoesNotExist:
        return Response(
            {"message": "Task not found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    transcript = get_transcript_id(task)
    if transcript is None:
        return Response(
            {"message": "Transcript not found."},
            status=status.HTTP_404_NOT_FOUND,
        )
    payload = transcript.payload["payload"]
    lines = []

    if export_type == "srt":
        for index, segment in enumerate(payload):
            lines.append(str(index + 1))
            lines.append(segment["start_time"] + " --> " + segment["end_time"])
            lines.append(segment["text"] + "\n")
        filename = "transcript.srt"
        content = "\n".join(lines)
    elif export_type == "vtt":
        lines.append("WEBVTT\n")
        for index, segment in enumerate(payload):
            lines.append(str(index + 1))
            lines.append(segment["start_time"] + " --> " + segment["end_time"])
            lines.append(segment["text"] + "\n")
        filename = "transcript.vtt"
        content = "\n".join(lines)
    elif export_type == "txt":
        for index, segment in enumerate(payload):
            lines.append(segment["text"] + "\n")
        filename = "transcript.txt"
        content = "\n".join(lines)
    elif export_type == "ytt":
        try:
            json_data = {
                "srt": transcript.payload,
                "url": task.video.url,
                "language": task.video.language,
            }
            response = requests.post(
                "http://216.48.183.5:7000/align_json",
                json=json_data,
            )
            data = response.json()

            ytt_genorator(data, "transcript_local.ytt", prev_line_in=0, mode="data")
            file_location = "transcript_local.ytt"
        except:
            return Response(
                {"message": "Error in exporting to ytt format."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        with open(file_location, "r") as f:
            file_data = f.read()
        response = HttpResponse(file_data, content_type="application/xml")
        response["Content-Disposition"] = 'attachment; filename="transcript.ytt"'
        return response

    else:
        return Response(
            {"message": "This type is not supported."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if len(content) == 0:
        content = " "
    content_type = "application/json"
    response = HttpResponse(content, content_type=content_type)
    response["Content-Disposition"] = 'attachment; filename="%s"' % filename
    response["filename"] = filename
    return response


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
            "language",
            openapi.IN_QUERY,
            description=("A string to pass the language of the transcript"),
            type=openapi.TYPE_STRING,
            required=True,
        ),
    ],
    responses={
        200: "Generates the transcript and returns the transcript id and payload from youtube"
    },
)
@api_view(["GET"])
def create_original_source_transcript(request):
    """
    Endpoint to get or generate(if not existing) a transcription for a video
    based on the youtube subtitles
    """
    if ("language" or "video_id") not in dict(request.query_params):
        return Response(
            {"message": "missing param : video_id or language"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    video_id = request.query_params["video_id"]
    lang = request.query_params["language"]
    transcript = (
        Transcript.objects.filter(video_id__exact=video_id)
        .filter(language=lang)
        .filter(transcript_type=ORIGINAL_SOURCE)
    )

    if transcript:
        # Filter the transcript where the type is ORIGINAL_SOURCE
        transcript = transcript.order_by("-updated_at").first()

        return Response(
            {"id": transcript.id, "data": transcript.payload}, status=status.HTTP_200_OK
        )

    else:
        # generate transcript using Youtube captions
        try:
            video = Video.objects.get(pk=video_id)
        except Video.DoesNotExist:
            return Response(
                {"message": "Video not found"}, status=status.HTTP_404_NOT_FOUND
            )
        subtitles = video.subtitles
        if subtitles is not None:
            transcript_obj = Transcript(
                transcript_type=ORIGINAL_SOURCE,
                video=video,
                language=lang,
                payload=subtitles,
            )
            transcript_obj.save()

            return Response(
                {"id": transcript_obj.id, "data": transcript_obj.payload},
                status=status.HTTP_200_OK,
            )
        else:
            return Response(
                {"message": "No subtitles found."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


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
    ],
    responses={200: "Returns the transcription for a particular video."},
)
@api_view(["GET"])
def retrieve_transcription(request):
    """
    Endpoint to retrive a transcription for a transcription entry
    """

    # Check if video_id and language and transcript_type has been passed
    if "video_id" not in dict(request.query_params):
        return Response(
            {"message": "missing param : video_id"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    video_id = request.query_params["video_id"]
    user_id = request.user.id

    try:
        video = Video.objects.get(pk=video_id)
    except Video.DoesNotExist:
        return Response(
            {"message": "Video not found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    # Get the latest transcript
    transcript = Transcript.objects.filter(video_id__exact=video_id)

    if transcript.filter(status="TRANSCRIPTION_REVIEW_COMPLETE").first() is not None:
        transcript_obj = transcript.filter(
            status="TRANSCRIPTION_REVIEW_COMPLETE"
        ).first()
        return Response(
            {"id": transcript_obj.id, "data": transcript_obj.payload},
            status=status.HTTP_200_OK,
        )
    elif transcript.filter(status="TRANSCRIPTION_EDIT_COMPLETE").first() is not None:
        transcript_obj = transcript.filter(status="TRANSCRIPTION_EDIT_COMPLETE").first()
        return Response(
            {"id": transcript_obj.id, "data": transcript_obj.payload},
            status=status.HTTP_200_OK,
        )
    else:
        return Response(
            {"message": "No transcript found"}, status=status.HTTP_404_NOT_FOUND
        )


def generate_transcription(video, lang, user, transcript_type, task, payload):
    status = TRANSCRIPTION_SELECT_SOURCE
    transcript_obj = Transcript(
        transcript_type=transcript_type,
        video=video,
        language=lang,
        payload=payload,
        user=user,
        task=task,
        status=status,
    )
    transcript_obj.save()
    return {
        "transcript_id": transcript_obj.id,
        "data": transcript_obj.payload,
        "task_id": task.id,
    }


def get_transcript_id(task):
    transcript = Transcript.objects.filter(task=task)
    if "EDIT" in task.task_type:
        if task.status == "NEW":
            transcript_id = None
        if task.status == "SELECTED_SOURCE":
            transcript_id = (
                transcript.filter(video=task.video)
                .filter(status="TRANSCRIPTION_SELECT_SOURCE")
                .first()
            )
        if task.status == "INPROGRESS":
            transcript_id = (
                transcript.filter(video=task.video)
                .filter(status="TRANSCRIPTION_EDIT_INPROGRESS")
                .first()
            )
        if task.status == "COMPLETE":
            transcript_id = (
                transcript.filter(video=task.video)
                .filter(status="TRANSCRIPTION_EDIT_COMPLETE")
                .first()
            )
    else:
        if task.status == "NEW":
            transcript_id = (
                transcript.filter(video=task.video)
                .filter(status="TRANSCRIPTION_REVIEWER_ASSIGNED")
                .first()
            )
        if task.status == "INPROGRESS":
            transcript_id = (
                transcript.filter(video=task.video)
                .filter(status="TRANSCRIPTION_REVIEW_INPROGRESS")
                .first()
            )
        if task.status == "COMPLETE":
            transcript_id = (
                transcript.filter(video=task.video)
                .filter(status="TRANSCRIPTION_REVIEW_COMPLETE")
                .first()
            )
    return transcript_id


@swagger_auto_schema(
    method="get",
    manual_parameters=[
        openapi.Parameter(
            "task_id",
            openapi.IN_QUERY,
            description=("An integer to pass the task id"),
            type=openapi.TYPE_INTEGER,
            required=True,
        ),
    ],
    responses={200: "Returns the initial transcription after source is selected."},
)
@api_view(["GET"])
def get_payload(request):
    try:
        task_id = request.query_params["task_id"]
    except KeyError:
        return Response(
            {"message": "Missing required parameters - task_id"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        task = Task.objects.get(pk=task_id)
    except Task.DoesNotExist:
        return Response(
            {"message": "Task doesn't exist."},
            status=status.HTTP_404_NOT_FOUND,
        )

    transcript = get_transcript_id(task)
    if transcript is None:
        return Response(
            {"message": "Transcript not found."},
            status=status.HTTP_404_NOT_FOUND,
        )
    else:
        transcript_id = transcript.id

    # Retrieve the transcript object
    try:
        transcript = Transcript.objects.get(pk=transcript_id)
    except Transcript.DoesNotExist:
        return Response(
            {"message": "Transcript doesn't exist."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    return Response(
        {"payload": transcript.payload, "source_type": transcript.transcript_type},
        status=status.HTTP_200_OK,
    )


def change_active_status_of_next_tasks(task, transcript_obj):
    tasks = Task.objects.filter(video=task.video)
    activate_translations = True

    if (
        "EDIT" in task.task_type
        and tasks.filter(task_type="TRANSCRIPTION_REVIEW").first()
    ):
        activate_translations = False
        tasks.filter(task_type="TRANSCRIPTION_REVIEW").update(is_active=True)
        transcript = (
            Transcript.objects.filter(video=task.video)
            .filter(status="TRANSCRIPTION_REVIEWER_ASSIGNED")
            .first()
        )

        if transcript is not None:
            transcript.parent_transcript = transcript_obj
            transcript.payload = transcript_obj.payload
            transcript.save()

    if activate_translations and tasks.filter(task_type="TRANSLATION_EDIT").first():
        tasks.filter(task_type="TRANSLATION_EDIT").update(is_active=True)
        translations = Translation.objects.filter(video=task.video).filter(
            status="TRANSLATION_SELECT_SOURCE"
        )
        if translations.first() is not None:
            for translation in translations:
                project = Project.objects.get(id=task.video.project_id.id)
                organization = project.organization_id
                source_type = (
                    project.default_translation_type
                    or organization.default_translation_type
                )
                if source_type == None:
                    source_type = "MACHINE_GENERATED"
                payloads = generate_translation_payload(
                    transcript_obj, translation.target_language, [source_type]
                )
                translation.payload = payloads[source_type]
                translation.transcript = transcript_obj
                translation.save()
    else:
        print("No change in status")


@swagger_auto_schema(
    method="post",
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        required=["payload", "task_id"],
        properties={
            "task_id": openapi.Schema(
                type=openapi.TYPE_INTEGER,
                description="An integer identifying the task instance",
            ),
            "payload": openapi.Schema(
                type=openapi.TYPE_OBJECT,
                description="A string to pass the transcript data",
            ),
            "final": openapi.Schema(
                type=openapi.TYPE_BOOLEAN,
                description="A boolean to pass check whether to allow user to load latest transcript",
            ),
        },
        description="Post request body for projects which have save_type == new_record",
    ),
    responses={
        200: "Transcript has been saved successfully",
    },
)
@api_view(["POST"])
def save_transcription(request):
    """
    Endpoint to save a transcript for a video
    Request body:
    {
        "transcript_id": "",
        "payload": "",
        "task_id" : ""
    }
    """
    # Collect the request parameters
    try:
        transcript_id = request.data.get("transcript_id", None)
        task_id = request.data["task_id"]
        payload = request.data["payload"]
    except KeyError:
        return Response(
            {"message": "Missing required parameters - payload or task_id"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        task = Task.objects.get(pk=task_id)
    except Task.DoesNotExist:
        return Response(
            {"message": "Task doesn't exist."},
            status=status.HTTP_404_NOT_FOUND,
        )

    if not task.is_active:
        return Response(
            {"message": "This task is not ative yet."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    transcript = get_transcript_id(task)

    if transcript is None:
        return Response(
            {"message": "Transcript not found."},
            status=status.HTTP_404_NOT_FOUND,
        )
    else:
        transcript_id = transcript.id

    # Retrieve the transcript object
    try:
        transcript = Transcript.objects.get(pk=transcript_id)

        # Check if the transcript has a user
        if task.user != request.user:
            return Response(
                {"message": "You are not allowed to update this transcript."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        else:
            if transcript.status == TRANSCRIPTION_REVIEW_COMPLETE:
                return Response(
                    {
                        "message": "Transcript can't be edited, as the final transcript already exists"
                    },
                    status=status.HTTP_201_CREATED,
                )

            if "EDIT" in task.task_type:
                if request.data.get("final"):
                    if (
                        Transcript.objects.filter(status=TRANSCRIPTION_EDIT_COMPLETE)
                        .filter(video=task.video)
                        .first()
                        is not None
                    ):
                        return Response(
                            {"message": "Final Edited Transcript already submitted."},
                            status=status.HTTP_201_CREATED,
                        )
                    tc_status = TRANSCRIPTION_EDIT_COMPLETE
                    transcript_type = transcript.transcript_type
                    transcript_obj = Transcript.objects.create(
                        transcript_type=transcript_type,
                        parent_transcript=transcript,
                        video=transcript.video,
                        language=transcript.language,
                        payload=payload,
                        user=request.user,
                        task=task,
                        status=tc_status,
                    )
                    task.status = "COMPLETE"
                    task.save()
                    change_active_status_of_next_tasks(task, transcript_obj)
                else:
                    transcript_obj = (
                        Transcript.objects.filter(status=TRANSCRIPTION_EDIT_INPROGRESS)
                        .filter(video=task.video)
                        .first()
                    )
                    tc_status = TRANSCRIPTION_EDIT_INPROGRESS
                    if transcript_obj is not None:
                        transcript_obj.payload = payload
                        transcript_obj.transcript_type = transcript_obj.transcript_type
                        transcript_obj.save()
                    else:
                        transcript_obj = (
                            Transcript.objects.filter(
                                status=TRANSCRIPTION_SELECT_SOURCE
                            )
                            .filter(video=task.video)
                            .first()
                        )
                        if transcript_obj is None:
                            return Response(
                                {"message": "Transcript object does not exist."},
                                status=status.HTTP_404_NOT_FOUND,
                            )
                        transcript_obj = Transcript.objects.create(
                            transcript_type=transcript_obj.transcript_type,
                            parent_transcript=transcript_obj,
                            video=task.video,
                            language=transcript_obj.language,
                            payload=payload,
                            user=request.user,
                            task=task,
                            status=tc_status,
                        )
                        task.save()
            else:
                if request.data.get("final"):
                    if (
                        Transcript.objects.filter(status=TRANSCRIPTION_REVIEW_COMPLETE)
                        .filter(video=task.video)
                        .first()
                    ):
                        return Response(
                            {"message": "Reviewed Transcription already exists."},
                            status=status.HTTP_201_CREATED,
                        )
                    else:
                        tc_status = TRANSCRIPTION_REVIEW_COMPLETE
                        transcript_obj = Transcript.objects.create(
                            transcript_type=transcript.transcript_type,
                            parent_transcript=transcript,
                            video=transcript.video,
                            language=transcript.language,
                            payload=payload,
                            user=request.user,
                            task=task,
                            status=tc_status,
                        )
                        task.status = "COMPLETE"
                        task.save()
                        change_active_status_of_next_tasks(task, transcript_obj)
                else:
                    tc_status = TRANSCRIPTION_REVIEW_INPROGRESS
                    transcript_type = transcript.transcript_type
                    transcript_obj = (
                        Transcript.objects.filter(
                            status=TRANSCRIPTION_REVIEW_INPROGRESS
                        )
                        .filter(video=task.video)
                        .first()
                    )
                    if transcript_obj is not None:
                        transcript_obj.payload = payload
                        transcript_obj.transcript_type = transcript_type
                        transcript_obj.save()
                    else:
                        transcript_obj = Transcript.objects.create(
                            transcript_type=transcript_type,
                            parent_transcript=transcript,
                            video=transcript.video,
                            language=transcript.language,
                            payload=payload,
                            user=request.user,
                            task=task,
                            status=tc_status,
                        )
                        task.status = "INPROGRESS"
                        task.save()

            if request.data.get("final"):
                return Response(
                    {
                        "task_id": task_id,
                        "transcript_id": transcript_obj.id,
                        "data": transcript_obj.payload,
                        "message": "Transcript is submitted.",
                    },
                    status=status.HTTP_200_OK,
                )
            else:
                return Response(
                    {
                        "task_id": task_id,
                        "transcript_id": transcript_obj.id,
                        "data": transcript_obj.payload,
                    },
                    status=status.HTTP_200_OK,
                )

    except Transcript.DoesNotExist:
        return Response(
            {"message": "Transcript doesn't exist."},
            status=status.HTTP_400_BAD_REQUEST,
        )


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
    ],
    responses={200: "Json is generated"},
)
@api_view(["GET"])
def get_word_aligned_json(request):
    video_id = request.query_params.get("video_id")

    if video_id is None:
        return Response(
            {"message": "missing param : video_id"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        video = Video.objects.get(pk=video_id)
    except Video.DoesNotExist:
        return Response(
            {"message": "Video not found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    transcript = Transcript.objects.filter(video=video)
    if transcript.filter(status="TRANSCRIPTION_REVIEW_COMPLETE").first() != None:
        transcript_obj = transcript.filter(
            status="TRANSCRIPTION_REVIEW_COMPLETE"
        ).first()
    elif transcript.filter(status="TRANSCRIPTION_REVIEW_INPROGRESS").first() != None:
        transcript_obj = transcript.filter(
            status="TRANSCRIPTION_REVIEW_INPROGRESS"
        ).first()
    elif transcript.filter(status="TRANSCRIPTION_REVIEWER_ASSIGNED").first() != None:
        transcript_obj = transcript.filter(
            status="TRANSCRIPTION_REVIEWER_ASSIGNED"
        ).first()
    elif transcript.filter(status="TRANSCRIPTION_EDIT_COMPLETE").first() != None:
        transcript_obj = transcript.filter(status="TRANSCRIPTION_EDIT_COMPLETE").first()
    elif transcript.filter(status="TRANSCRIPTION_EDIT_INPROGRESS").first() != None:
        transcript_obj = transcript.filter(
            status="TRANSCRIPTION_EDIT_INPROGRESS"
        ).first()
    elif transcript.filter(status="TRANSCRIPTION_EDITOR_ASSIGNED").first() != None:
        transcript_obj = transcript.filter(
            status="TRANSCRIPTION_EDITOR_ASSIGNED"
        ).first()
    elif transcript.filter(status="TRANSCRIPTION_SELECT_SOURCE").first() != None:
        transcript_obj = transcript.filter(status="TRANSCRIPTION_SELECT_SOURCE").first()
    else:
        return Response(
            {"message": "Transcript not found for this video."},
            status=status.HTTP_404_NOT_FOUND,
        )

    try:
        payload = transcript_obj.payload
        json_data = {
            "srt": transcript_obj.payload,
            "url": video.url,
            "language": video.language,
        }
        response = requests.post(
            "http://216.48.183.5:7000/align_json",
            json=json_data,
        )
        data = response.json()

        for i in range(len(payload["payload"])):
            data[str(i + 1)]["start_time"] = payload["payload"][i]["start_time"]
            data[str(i + 1)]["end_time"] = payload["payload"][i]["end_time"]

        if len(data) == 0:
            data = {}
        data["message"] = "Transcript is word aligned."

        return Response(
            data,
            status=status.HTTP_200_OK,
        )
    except:
        return Response(
            {"message": "Error in getting json format."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["GET"])
def get_supported_languages(request):
    """
    Endpoint to get the supported languages for ASR API
    """

    # Make a call to the FASTAPI endpoint to get the list of supported languages
    try:
        return Response(
            [
                {"label": label, "value": value}
                for label, value in get_asr_supported_languages().items()
            ],
            status=status.HTTP_200_OK,
        )
    except Exception:
        return Response(
            {"message": "Error while calling ASR API"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["GET"])
def get_transcript_types(request):
    """
    Fetches all transcript types.
    """
    data = [
        {"label": transcript_type[1], "value": transcript_type[0]}
        for transcript_type in TRANSCRIPT_TYPE
    ]
    return Response(data, status=status.HTTP_200_OK)


## Define the Transcript ViewSet
class TranscriptViewSet(ModelViewSet):
    """
    API ViewSet for the Transcript model.
    Performs CRUD operations on the Transcript model.
    Endpoint: /transcript/api/
    Methods: GET, POST, PUT, DELETE
    """

    queryset = Transcript.objects.all()
    serializer_class = TranscriptSerializer
