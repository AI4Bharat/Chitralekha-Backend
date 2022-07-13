import requests

from rest_framework.response import Response
from rest_framework import status
from rest_framework.viewsets import ModelViewSet
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated

from video.models import Video
from .models import *
from .serializers import TranscriptSerializer

## Utility Functions
def make_asr_api_call(url, lang, vad_level=2, chunk_size=10):
    try:
        headers = {
            "accept": "application/json",
        }
        json_data = {
            "url": url,
            "vad_level": vad_level,
            "chunk_size": chunk_size,
            "language": lang,
        }
        request_url = "http://216.48.182.174:5000/transcribe"
        response = requests.post(request_url, headers=headers, json=json_data)

        return response.json()
    except:
        return None


# Define the API views
@api_view(["GET"])
def create_transcription(request):
    # sourcery skip: remove-redundant-if, remove-unreachable-code
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
    transcript = Transcript.objects.filter(video_id__exact=video_id).filter(
        language=lang
    )
    # TODO: Check if this is the expected workflow? In this case, if only a machine
    # generated transcript exists, the second filtering in the if block returns nothing
    if transcript:

        # Filter the transcript where the type is ORIGINAL_SOURCE
        transcript = (
            transcript.filter(transcript_type=ORIGINAL_SOURCE)
            .order_by("-updated_at")
            .first()
        )

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

        # Check if the load latest transcript flag is set to true
        if load_latest_transcript == "true":

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
                UPDATED_ORIGINAL_SOURCE if transcript.transcript_type == ORIGINAL_SOURCE else UPDATED_MACHINE_GENERATED
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
        transcript_obj = Transcript(
            transcript_type=UPDATED_MACHINE_GENERATED,
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
        headers = {"Content-Type": "application/json"}
        request_url = "http://216.48.182.174:5000/supported_languages"
        response = requests.get(url=request_url, headers=headers, verify=False)
        response_data = response.json()
        return Response({"data": response_data}, status=status.HTTP_200_OK)
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
