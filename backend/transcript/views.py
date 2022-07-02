from rest_framework.response import Response
from rest_framework import status
from rest_framework.viewsets import ModelViewSet
from rest_framework.decorators import api_view
from rest_framework.permissions import IsAuthenticatedOrReadOnly

import requests

from .models import *
from video.models import Video
from .serializers import TranscriptSerializer

## Utility Functions 
def make_asr_api_call(url, lang):
    try:
        headers = {"Content-Type": "application/json"}
        body = {"url": url, "language": lang}
        request_url = "http://216.48.181.177:5050/transcribe"
        response = requests.post(url=request_url, headers = headers, json = body,verify=False)
        response_data = json.loads(response.content)
        return response_data
    except Exception as e:
        return None

# Define the API views 
@api_view(['GET'])
def create_transcription(request):
    """
    Endpoint to get or generate(if not existing) a transcription for a video
    """
    if "video_id" in dict(request.query_params):
        video_id = request.query_params["video_id"]
        lang = request.query_params["language"]
        transcript = Transcript.objects.filter(video_id__exact = video_id).filter(language=lang)
    else:
        return Response({"message": "missing param : video_id"}, status=status.HTTP_400_BAD_REQUEST)

    if transcript:
        transcript_serializer = TranscriptSerializer(transcript)
        return Response({"data": transcript_serializer.data['payload']}, status=status.HTTP_200_OK)
    else:
        # generate transcript using ASR API
        video = Video.objects.get(pk=video_id)
        transcribed_data = make_asr_api_call(video.url, lang)
        if transcribed_data is not None:
            transcript_obj = Transcript(transcript_type=MACHINE_GENERATED, video=video, language=lang, payload=transcribed_data)
            transcript_obj.save()
            return Response({"data": transcript_obj.payload}, status=status.HTTP_200_OK)
        else:
            return Response({"message": "Error while calling ASR API"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


## Define the Transcript ViewSet
class TranscriptViewSet(ModelViewSet):
    '''
    API ViewSet for the Transcript model.
    Performs CRUD operations on the Video model.
    Endpoint: /transcript/api/
    Methods: GET, POST, PUT, DELETE
    '''
    queryset = Transcript.objects.all()
    serializer_class = TranscriptSerializer
    # permission_classes = (IsAuthenticatedOrReadOnly,)

    