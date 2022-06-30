from datetime import timedelta
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.permissions import IsAuthenticatedOrReadOnly
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet
from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

from .models import Video
from .serializers import VideoSerializer

# Define the YouTube Downloader object
ydl = YoutubeDL({'format': 'best'})

@api_view(['GET'])
def get_video(request):
    '''
    API Endpoint to get the direct URL to a video
    Endpoint: /video/
    Method: GET
    Query Params: video_url (required)
    '''

    # Get the video URL from the query params
    url = request.query_params.get('video_url')
    if url is None:
        return Response({
            'error': 'Video URL not provided in query params.'
        }, status=status.HTTP_400_BAD_REQUEST)

    # Get the video info from the YouTube API
    try:
        info = ydl.extract_info(url, download=False)
    except DownloadError:
        return Response({
            'error': f'{url} is an invalid video URL.'
        }, status=status.HTTP_400_BAD_REQUEST)

    # Extract required data from the video info
    normalized_url = info['webpage_url']
    title = info['title']
    duration = timedelta(seconds=info['duration'])

    # Create a new DB entry if URL does not exist, else return the existing entry
    video, created = Video.objects.get_or_create(url=normalized_url, defaults={'name':title, 'duration':duration})
    if created:
        video.save()

    # Return the Direct URL to the video
    direct_url = info['url']
    return Response({
        'direct_url': direct_url,
    }, status=status.HTTP_200_OK)


class VideoViewSet(ModelViewSet):
    '''
    API ViewSet for the Video model.
    Performs CRUD operations on the Video model.
    Endpoint: /video/api/
    Methods: GET, POST, PUT, DELETE
    '''
    queryset = Video.objects.all()
    serializer_class = VideoSerializer
    permission_classes = (IsAuthenticatedOrReadOnly,)
