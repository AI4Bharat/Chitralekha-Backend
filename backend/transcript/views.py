from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet
from video.models import Video
from task.models import Task

from .models import (
    Transcript,
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
        openapi.Parameter(
            "load_latest_transcript",
            openapi.IN_QUERY,
            description=(
                "A boolean to pass check whether to allow user to load latest transcript"
            ),
            type=openapi.TYPE_BOOLEAN,
            required=False,
        ),
    ],
    responses={200: "Returns the transcription for a particular video and language"},
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


@swagger_auto_schema(
    method="post",
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        required=["payload", "task_id", "transcript_id", "video_id"],
        properties={
            "transcript_id": openapi.Schema(
                type=openapi.TYPE_STRING,
                description="A uuid string identifying the transcript instance",
            ),
            "task_id": openapi.Schema(
                type=openapi.TYPE_INTEGER,
                description="An integer identifying the task instance",
            ),
            "payload": openapi.Schema(
                type=openapi.TYPE_STRING,
                description="A string to pass the transcript data",
            ),
            "video_id": openapi.Schema(
                type=openapi.TYPE_INTEGER,
                description="An integer to pass the video ID",
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
        "video_id": "",
        "task_id" : ""
    }
    """

    # Collect the request parameters
    try:
        transcript_id = request.data["transcript_id"]
        task_id = request.data["task_id"]
        video_id = request.data["video_id"]
        payload = request.data["payload"]
    except KeyError:
        return Response(
            {
                "message": "Missing required parameters - language or payload or task_id or transcript_id"
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        video = Video.objects.get(pk=video_id)
    except Video.DoesNotExist:
        return Response(
            {"message": "Video doesn't exist."},
            status=status.HTTP_404_NOT_FOUND,
        )

    try:
        task = Task.objects.get(pk=task_id)
    except Task.DoesNotExist:
        return Response(
            {"message": "Task doesn't exist."},
            status=status.HTTP_404_NOT_FOUND,
        )

    # Retrieve the transcript object
    try:
        transcript = Transcript.objects.filter(pk=transcript_id).first()

        # Check if the transcript has a user
        if transcript.user != request.user:
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

            if transcript.transcript_type == ORIGINAL_SOURCE:
                updated_transcript_type = UPDATED_ORIGINAL_SOURCE
            elif transcript.transcript_type == MACHINE_GENERATED:
                updated_transcript_type = UPDATED_MACHINE_GENERATED
            else:
                updated_transcript_type = UPDATED_MANUALLY_CREATED

            if "EDIT" in task.task_type:
                if request.data.get("final"):
                    tc_status = TRANSCRIPTION_EDIT_COMPLETE
                    task.status = "COMPLETE"
                    task.save()
                    transcript_type = updated_transcript_type
                else:
                    tc_status = TRANSCRIPTION_EDIT_INPROGRESS
                    transcript_type = transcript.transcript_type

                transcript_obj = Transcript(
                    transcript_type=transcript_type,
                    parent_transcript=transcript,
                    video=video,
                    language=transcript.language,
                    payload=payload,
                    user=request.user,
                    task=task,
                    status=tc_status,
                )
            else:
                if request.data.get("final"):
                    tc_status = TRANSCRIPTION_REVIEW_COMPLETE
                    task.status = "COMPLETE"
                    task.save()
                    transcript_type = updated_transcript_type
                else:
                    tc_status = TRANSCRIPTION_REVIEW_INPROGRESS
                    transcript_type = transcript.transcript_type

                transcript_obj = Transcript(
                    transcript_type=transcript_type,
                    parent_transcript=transcript,
                    video=video,
                    language=transcript.language,
                    payload=payload,
                    user=request.user,
                    task=task,
                    status=tc_status,
                )
            # Save the updated transcript object
            transcript_obj.save()

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


@api_view(["GET"])
def get_supported_languages(request):
    """
    Endpoint to get the supported languages for ASR API
    """

    # Make a call to the FASTAPI endpoint to get the list of supported languages
    try:
        return Response(
            {"data": get_asr_supported_languages()}, status=status.HTTP_200_OK
        )
    except Exception:
        return Response(
            {"message": "Error while calling ASR API"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


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
