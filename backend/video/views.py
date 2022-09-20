from datetime import timedelta
from io import StringIO

import requests
import urllib
import webvtt
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.permissions import IsAuthenticatedOrReadOnly
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet
from transcript.models import ORIGINAL_SOURCE, Transcript
from translation.models import Translation
from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

from .models import Video
from .serializers import VideoSerializer
from .utils import extract_google_drive_link_id

# Define the YouTube Downloader object
ydl = YoutubeDL({"format": "best"})

@swagger_auto_schema(
    method="get",
    manual_parameters=[
        openapi.Parameter(
            "video_url",
            openapi.IN_QUERY,
            description=("A string to pass the url of the video to be transcribed"),
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
            "save_original_transcript",
            openapi.IN_QUERY,
            description=(
                "A boolean to pass whether or not to create a YouTube transcript"
            ),
            type=openapi.TYPE_BOOLEAN,
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
    Query Params: video_url (required)
    """

    # Get the video URL from the query params
    url = request.query_params.get("video_url")
    lang = request.query_params.get("lang", "en")
    is_audio_only = request.query_params.get("is_audio_only", "false")

    # Convert audio only to boolean
    is_audio_only = is_audio_only.lower() == "true"
    if url is None:
        return Response(
            {"error": "Video URL not provided in query params."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    ## TEMP: Handle audio_only files separately for google drive links
    if "drive.google.com" in url and is_audio_only:

        # Construct a direct download link from the google drive url 
        # get the id from the drive link 
        file_id = extract_google_drive_link_id(url)
        if not file_id["valid"]:
            return Response(
                {"error": file_id["data"]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        url = f"https://drive.google.com/uc?export=download&confirm=yTib&id={file_id['data']}"
        print("FILE ID", file_id["data"])
        # Get the video metadata
        title = urllib.request.urlopen(urllib.request.Request(url)).info().get_filename()
        direct_audio_url = url

        # Set duration to 0
        duration = timedelta(seconds=0)

        # Create a new DB entry if URL does not exist, else return the existing entry
        video, created = Video.objects.get_or_create(
            url=url, defaults={"name": title, "duration": duration, "audio_only": is_audio_only}
        )
        if created:
            # Save the subtitles to the video object
            video.subtitles = {
                "status": "SUCCESS",
                "output": None,
            }
            video.save()

        return Response(
            {
                "video": VideoSerializer(video).data,
                "direct_audio_url": direct_audio_url,
            },
            status=status.HTTP_200_OK,
        )

    # Get the video info from the YouTube API
    try:
        info = ydl.extract_info(url, download=False)
    except DownloadError:
        return Response(
            {"error": f"{url} is an invalid video URL."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Check if the link is for Google Drive or YouTube
    if "drive.google.com" in url:

        # Get the file ID from the URL
        file_id = info["id"]

        # Create a direct download link by extracting the ID from the URL
        # and appending it to the Google Drive direct download link
        url = "https://drive.google.com/uc?export=download&confirm=yTib&id=" + file_id
        info["url"] = url
        info["webpage_url"] = "https://drive.google.com/file/d/" + file_id

    # Extract required data from the video info
    normalized_url = info["webpage_url"]
    title = info["title"]
    duration = timedelta(seconds=info["duration"])

    # Create a new DB entry if URL does not exist, else return the existing entry
    video, created = Video.objects.get_or_create(
        url=normalized_url, defaults={"name": title, "duration": duration, "audio_only": is_audio_only}
    )
    if created:
        video.save()

    # Return the Direct URL to the video
    direct_video_url = info["url"]

    subtitles = None
    if "subtitles" in info:
        if lang in info["subtitles"]:
            # If it's named "English"
            subtitles = info["subtitles"][lang]
        else:
            # If it has a custom name like "English transcript by NPTEL"
            for s_key in info["subtitles"]:
                if s_key.startswith(lang + "-"):
                    subtitles = info["subtitles"][s_key]
                    break

    # If manual captions not found, search for ASR transcripts
    if not subtitles and "automatic_captions" in info and lang in info["automatic_captions"]:
        subtitles = info["automatic_captions"][lang]

    subtitle_payload = None
    subtitles_list = []
    if subtitles:
        # Get the VTT URL from the subtitle info and make a GET request to fetch the data
        subtitle_url = [item["url"] for item in subtitles if item["ext"] == "vtt"][0]
        subtitle_payload = requests.get(subtitle_url).text

        # Parse the VTT file contents and append to the subtitle list
        subtitles_list.extend({"start": caption.start, "end": caption.end, "text": caption.text} for caption in webvtt.read_buffer(StringIO(subtitle_payload)))

    # Save the subtitles to the video object
    video.subtitles = {
        "status": "SUCCESS",
        "output": subtitle_payload,
    }
    video.save()

    # Get the direct audio URL
    for fmt in info["formats"]:
        if (
            fmt["resolution"] == "audio only"
            and fmt["ext"] == "m4a"
            and fmt["quality"] == 3
        ):
            direct_audio_url = fmt["url"]
            break

    # Create the response data to be returned
    serializer = VideoSerializer(video)
    response_data = {
        "subtitles": subtitles_list,
        "video": serializer.data,
    }

    # Check if the user passed a boolean to create the transcript
    save_original_transcript = request.query_params.get(
        "save_original_transcript", "false"
    )

    # Convert to boolean
    save_original_transcript = save_original_transcript.lower() == "true"

    if save_original_transcript:

        # Check if the transcription for the video already exists
        transcript = (
            Transcript.objects.filter(video=video)
            .filter(language=lang)
            .filter(transcript_type=ORIGINAL_SOURCE)
            .first()
        )

        if not transcript:

            # Save a transcript object
            transcript = Transcript(
                transcript_type=ORIGINAL_SOURCE,
                video=video,
                language=lang,
                payload=video.subtitles,
            )
            transcript.save()

        # Add the transcript to the response data
        response_data["transcript_id"] = transcript.id

    # Check if it's audio only
    if is_audio_only:
        response_data["audio_url"] = direct_audio_url
    else:
        response_data["video_url"] = direct_video_url

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
        filtered_transcript_ids = [
            transcript[2] for transcript in recent_transcripts
        ]

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


class VideoViewSet(ModelViewSet):
    """
    API ViewSet for the Video model.
    Performs CRUD operations on the Video model.
    Endpoint: /video/api/
    Methods: GET, POST, PUT, DELETE
    """

    queryset = Video.objects.all()
    serializer_class = VideoSerializer
    permission_classes = (IsAuthenticatedOrReadOnly,)
