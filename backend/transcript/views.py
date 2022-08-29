from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet
from video.models import Video

from .models import *
from .serializers import TranscriptSerializer
from .utils.asr import get_asr_supported_languages, make_asr_api_call


# Define the API views
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
        200: "Generates the transcript and returns the transcript id and payload"
    },
)
@api_view(["GET"])
def create_transcription(request):
    """
    Endpoint to get or generate(if not existing) a transcription for a video
    """
    if ("language" or "video_id") not in dict(request.query_params):
        return Response(
            {"message": "missing param : video_id or language"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    video_id = request.query_params["video_id"]
    lang = request.query_params["language"]
    transcript = (
        Transcript.objects.filter(video_id=video_id)
        .filter(language=lang)
        .filter(transcript_type=MACHINE_GENERATED)
    )
    if transcript:

        # Filter the transcript where the type is MACHINE_GENERATED
        transcript = transcript.order_by("-updated_at").first()

        return Response(
            {"id": transcript.id, "data": transcript.payload}, status=status.HTTP_200_OK
        )

    else:
        # generate transcript using ASR API
        try:
            video = Video.objects.get(pk=video_id)
        except Video.DoesNotExist:
            return Response(
                {"message": "Video not found"}, status=status.HTTP_404_NOT_FOUND
            )
        transcribed_data = make_asr_api_call(video.url, lang)
        if transcribed_data is not None:
            transcript_obj = Transcript(
                transcript_type=MACHINE_GENERATED,
                video=video,
                language=lang,
                payload=transcribed_data,
            )
            transcript_obj.save()

            return Response(
                {"id": transcript_obj.id, "data": transcript_obj.payload},
                status=status.HTTP_200_OK,
            )
        else:
            return Response(
                {"message": "Error while calling ASR API"},
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
def create_youtube_transcription(request):
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
            "language",
            openapi.IN_QUERY,
            description=("A string to pass the language of the transcript"),
            type=openapi.TYPE_STRING,
            required=True,
        ),
        openapi.Parameter(
            "transcript_type",
            openapi.IN_QUERY,
            description=("A string to pass the type of the transcript"),
            type=openapi.TYPE_STRING,
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
    if "language" not in dict(request.query_params):
        return Response(
            {"message": "missing param : language"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if "transcript_type" not in dict(request.query_params):
        return Response(
            {"message": "missing param : transcript_type"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    video_id = request.query_params["video_id"]
    lang = request.query_params["language"]
    transcript_type = request.query_params["transcript_type"]
    user_id = request.user.id

    # Get the latest transcript
    transcript = (
        Transcript.objects.filter(video_id__exact=video_id)
        .filter(language=lang)
        .filter(user=user_id)
        .filter(transcript_type=transcript_type)
        .first()
    )

    # Check if there are records in transcript
    if transcript:
        return Response(
            {"id": transcript.id, "data": transcript.payload},
            status=status.HTTP_200_OK,
        )

    else:
        try:
            load_latest_transcript = request.query_params["load_latest_transcript"]
        except:
            return Response(
                {"message": "You are not allowed to load this transcript."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Convert load_latest_transcript to boolean
        if type(load_latest_transcript) == str:
            load_latest_transcript = load_latest_transcript.lower() == "true"

        # Check if the load latest transcript flag is set to true
        if load_latest_transcript:

            # Get the latest transcript
            transcript = (
                Transcript.objects.filter(video_id=video_id)
                .filter(language=lang)
                .filter(transcript_type=transcript_type)
                .order_by("-updated_at")
                .first()
            )

            if transcript:
                return Response(
                    {"id": transcript.id, "data": transcript.payload},
                    status=status.HTTP_200_OK,
                )
            else:
                return Response(
                    {"message": "No transcript found"},
                    status=status.HTTP_404_NOT_FOUND,
                )
        else:
            return Response(
                {"message": "You are not allowed to load this transcript."},
                status=status.HTTP_400_BAD_REQUEST,
            )

@swagger_auto_schema(
    method="post",
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        required=["payload", "language"],
        properties={
            "transcript_id": openapi.Schema(
                type=openapi.TYPE_STRING,
                description="A uuid string identifying the transcript instance",
            ),
            "language": openapi.Schema(
                type=openapi.TYPE_STRING,
                description="A string to pass the language of the transcript",
            ),
            "payload": openapi.Schema(
                type=openapi.TYPE_STRING,
                description="A string to pass the transcript data",
            ),
            "video_id": openapi.Schema(
                type=openapi.TYPE_INTEGER,
                description="An integer to pass the video ID",
            ),
        },
        description="Post request body for projects which have save_type == new_record",
    ),
    responses={
        200: "Transcript has been saved successfully",
    },
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def save_transcription(request):
    """
    Endpoint to save a transcript for a video

    Request body:
    {
        "transcript_id": "",
        "language": "",
        "payload": "",
        "video_id": "",
    }
    """

    # Collect the request parameters
    transcript_id = request.data.get("transcript_id", None)
    language = request.data["language"]
    transcribed_data = request.data["payload"]
    user_id = request.user.id

    # Retrieve the transcript object
    try:
        transcript = Transcript.objects.get(pk=transcript_id)

        # Check if the transcript has a user
        if transcript.user is None:
            transcript_type = (
                UPDATED_ORIGINAL_SOURCE
                if transcript.transcript_type == ORIGINAL_SOURCE
                else UPDATED_MACHINE_GENERATED
            )
            # Create a new transcript object with the existing transcript as parent
            transcript_obj = Transcript(
                transcript_type=transcript_type,
                parent_transcript=transcript,
                video=transcript.video,
                language=language,
                payload=transcribed_data,
                user_id=user_id,
            )

            # Save the new transcript object
            transcript_obj.save()

            return Response(
                {"id": transcript_obj.id, "data": transcript_obj.payload},
                status=status.HTTP_200_OK,
            )

        else:
            # Update the transcript object with the new payload
            transcript.payload = transcribed_data
            transcript.save()

            return Response(
                {"id": transcript_id, "data": transcript.payload},
                status=status.HTTP_200_OK,
            )

    except Transcript.DoesNotExist:

        # Collect the video object
        video_id = request.data["video_id"]
        video = Video.objects.get(pk=video_id)

        # If transcript doesn't exist then save a new transcript object
        # TODO: Check if this is the expected transcript type?
        # FIX: The except block will never be reached. If reached, directly return an error.
        transcript_obj = Transcript(
            transcript_type=MANUALLY_CREATED,
            video=video,
            language=language,
            payload=transcribed_data,
            user_id=user_id,
        )

        # Save the new transcript object
        transcript_obj.save()

        return Response(
            {"id": transcript_obj.id, "data": transcript_obj.payload},
            status=status.HTTP_200_OK,
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
    Performs CRUD operations on the Video model.
    Endpoint: /transcript/api/
    Methods: GET, POST, PUT, DELETE
    """

    queryset = Transcript.objects.all()
    serializer_class = TranscriptSerializer
