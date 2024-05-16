from django.shortcuts import render
from rest_framework.decorators import (
    api_view,
    permission_classes,
    authentication_classes,
)
# Create your views here.
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import status
from rest_framework.decorators import (
    api_view,
    permission_classes,
    authentication_classes,
)
from rest_framework.response import Response
from task.models import Task

from datetime import datetime, timedelta

from config import voice_over_payload_offset_size, app_name

from django.db.models import Count, F, Sum
from operator import itemgetter
from itertools import groupby
from pydub import AudioSegment


@api_view(["GET"])
def get_voice_over_export_types(request):
    return Response(
        {"export_types": ["mp4", "mp3", "flac", "wav"]}, status=status.HTTP_200_OK
    )


@api_view(["GET"])
def get_translation_export_types(request):
    return Response(
        {"export_types": ["srt", "vtt", "txt", "docx", "docx-bilingual", "sbv", "TTML", "scc", "rt"]},
        status=status.HTTP_200_OK,
    )