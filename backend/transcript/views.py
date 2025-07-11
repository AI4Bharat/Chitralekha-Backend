import datetime
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import status
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from django.utils import timezone
from datetime import timedelta
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet
from video.models import Video
from task.models import Task
from rest_framework.decorators import action
from django.http import HttpResponse
from django.http import HttpRequest
import requests
from django.core.files.base import ContentFile
from json_to_ytt import *
from translation.models import Translation
from project.models import Project
from organization.models import Organization
from translation.utils import (
    get_batch_translations_using_indictrans_nmt_api,
    generate_translation_payload,
    translation_mg,
    convert_to_docx,
    convert_to_paragraph,
    convert_to_paragraph_with_images,
    convert_to_rt,
    convert_scc_format,
)
from .metadata import TRANSCRIPTION_LANGUAGE_CHOICES, TRANSCRIPTION_SUPPORTED_LANGUAGES
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

from voiceover.utils import get_bad_sentences_in_progress_for_transcription
from .decorators import is_transcript_editor
from .serializers import TranscriptSerializer
from .utils.asr import get_asr_supported_languages, make_asr_api_call
from .utils.TTML import generate_ttml
from .utils.ytt_align import *
from users.models import User
from rest_framework.response import Response
from functools import wraps
from rest_framework import status
from django.db.models import Q, Count, Avg, F, FloatField, BigIntegerField, Sum
from django.db.models.functions import Cast
from operator import itemgetter
from itertools import groupby
from django.core.cache import cache
import datetime
import math
import logging
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
import logging
from config import align_json_url, app_name
import regex
from .tasks import celery_align_json
from task.tasks import celery_nmt_call, celery_nmt_tts_call
import os
from .utils.timestamp import *
import openai
from utils.llm_api import get_model_output
from voiceover.models import VoiceOver
from django.utils.timezone import now

@api_view(["GET"])
def get_transcript_export_types(request):
    return Response(
        {
            "export_types": [
                "srt",
                "vtt",
                "txt",
                "docx",
                "mail-screenshot-docx",
                "ytt",
                "sbv",
                "TTML",
                "scc",
                "rt",
            ]
        },
        status=status.HTTP_200_OK,
    )


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
            description=("export type parameter srt/vtt/txt/docx/ytt/sbv/TTML/scc/rt"),
            type=openapi.TYPE_STRING,
            required=True,
        ),
        openapi.Parameter(
            "with_speaker_info",
            openapi.IN_QUERY,
            description=(
                "A boolean to determine whether to export with or without speaker info."
            ),
            type=openapi.TYPE_BOOLEAN,
            required=False,
        ),
    ],
    responses={200: "Transcript is exported"},
)
@api_view(["GET"])
def export_transcript(request):
    task_id = request.query_params.get("task_id")
    export_type = request.query_params.get("export_type")
    return_file_content = request.query_params.get("return_file_content")
    with_speaker_info = request.query_params.get("with_speaker_info", "false")
    with_speaker_info = with_speaker_info.lower() == "true"
    user_id = request.user.id
    user = User.objects.get(pk=user_id)

    if task_id is None or export_type is None:
        return Response(
            {"message": "missing param : task_id or export_type"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    supported_types = ["srt", "vtt", "txt", "docx", "mail-screenshot-docx", "ytt", "sbv", "TTML", "scc", "rt"]
    if export_type not in supported_types:
        return Response(
            {
                "message": "exported type only supported formats are : {srt, vtt, txt, docx, ytt, sbv, TTML, scc, rt}"
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
        try:
            if task.task_type == "TRANSLATION_VOICEOVER_EDIT" and task.status != "COMPLETE":
                voice_over_obj = VoiceOver.objects.filter(task=task).first()
                transcript = voice_over_obj.translation.transcript
            updated_payload = []
            index = 0
            for segment in voice_over_obj.payload["payload"].values():
                start_time = datetime.datetime.strptime(
                    segment["start_time"], "%H:%M:%S.%f"
                )
                end_time = datetime.datetime.strptime(segment["end_time"], "%H:%M:%S.%f")
                unix_start_time = datetime.datetime.timestamp(start_time)
                unix_end_time = datetime.datetime.timestamp(end_time)

                updated_segment = {
                    "start_time": segment["start_time"],
                    "end_time": segment["end_time"],
                    "text": segment["transcription_text"],
                    "speaker_id": "",
                    "unix_start_time": unix_start_time,
                    "unix_end_time": unix_end_time,
                    "image_url": segment.get("image_url"),
                }
                updated_payload.append(updated_segment)
            transcript.payload["payload"] = updated_payload
        except:
            return Response(
                {"message": "Transcript not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

    if with_speaker_info:
        speaker_info = transcript.video.multiple_speaker
        if speaker_info == False:
            return Response(
                {"message": "There is no speaker info in this transcript."},
                status=status.HTTP_400_BAD_REQUEST,
            )
    payload = transcript.payload["payload"]
    lines = []

    if export_type == "srt":
        for index, segment in enumerate(payload):
            if "text" in segment.keys():
                lines.append(str(index + 1))
                lines.append(segment["start_time"] + " --> " + segment["end_time"])
                if "verbatim_text" in segment.keys():
                    if len(segment.get("speaker_id", "")) > 0 and with_speaker_info:
                        lines.append(segment["speaker_id"] + ": " + segment["verbatim_text"] + "\n")
                    else:
                        lines.append(segment["verbatim_text"] + "\n")
                else:
                    if len(segment.get("speaker_id", "")) > 0 and with_speaker_info:
                        lines.append(segment["speaker_id"] + ": " + segment["text"] + "\n")
                    else:
                        lines.append(segment["text"] + "\n")
        filename = "transcript.srt"
        content = "\n".join(lines)
    elif export_type == "vtt":
        lines.append("WEBVTT\n")
        for index, segment in enumerate(payload):
            if "text" in segment.keys():
                lines.append(str(index + 1))
                lines.append(segment["start_time"] + " --> " + segment["end_time"])
                if "verbatim_text" in segment.keys():
                    if len(segment.get("speaker_id", "")) > 0 and with_speaker_info:
                        lines.append(segment["speaker_id"] + ": " + segment["verbatim_text"] + "\n")
                    else:
                        lines.append(segment["verbatim_text"] + "\n")
                else:
                    if len(segment.get("speaker_id", "")) > 0 and with_speaker_info:
                        lines.append(segment["speaker_id"] + ": " + segment["text"] + "\n")
                    else:
                        lines.append(segment["text"] + "\n")
        filename = "transcript.vtt"
        content = "\n".join(lines)
    elif export_type == "txt":
        for index, segment in enumerate(payload):
            if "text" in segment.keys():
                if "verbatim_text" in segment.keys():
                    lines.append(segment["verbatim_text"])
                else:
                    lines.append(segment["text"])
        filename = "transcript.txt"
        content = convert_to_paragraph(lines, task.video.name)
    elif export_type == "docx":
        for index, segment in enumerate(payload):
            if "text" in segment.keys():
                if "verbatim_text" in segment.keys():
                    lines.append(segment["verbatim_text"])
                else:
                    lines.append(segment["text"])
        filename = "transcript.txt"
        content = convert_to_paragraph(lines, task.video.name)
        return convert_to_docx(content)
    elif export_type == "mail-screenshot-docx":
        convert_to_paragraph_with_images.delay(payload, task.video.name, user.email, task_id, task.video.description)
        return Response(
            {"message": "Document will be emailed."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    elif export_type == "ytt":
        return Response(
            {"message": "Soemthing went wrong!."},
            status=status.HTTP_400_BAD_REQUEST,
        )
        if (
            transcript.payload != None
            and "payload" in transcript.payload.keys()
            and len(transcript.payload["payload"]) > 0
            and "ytt_azure_url" in transcript.payload.keys()
        ):
            file_location = transcript.payload["ytt_azure_url"].split("/")[-1]
            download_ytt_from_azure(file_location)
        else:
            try:
                data = align_json_api(transcript)
            except:
                return Response(
                    {
                        "message": "Error in exporting to ytt format as Align Json API is failing."
                    },
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )
                time_now = datetime.datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
                file_location = (
                    "{}_Video_{}_{}".format(app_name, transcript.video.id, time_now)
                    + ".ytt"
                )
            ytt_genorator(data, file_location, prev_line_in=0, mode="data")
            upload_ytt_to_azure(transcript, file_location)
        with open(file_location, "r") as f:
            file_data = f.read()
        response = HttpResponse(file_data, content_type="application/xml")
        response["Content-Disposition"] = 'attachment; filename="transcript.ytt"'
        if return_file_content:
            logging.info("Return File location")
            return Response(
                {"file_location": file_location},
                status=status.HTTP_200_OK,
            )
        os.remove(file_location)
        return response

    elif export_type == "sbv":
        for index, segment in enumerate(payload):
            if "verbatim_text" in segment.keys():
                lines.append(
                    segment["start_time"]
                    + ","
                    + segment["end_time"]
                    + "\n"
                    + segment["verbatim_text"]
                    + "\n"
                )
            else:
                lines.append(
                    segment["start_time"]
                    + ","
                    + segment["end_time"]
                    + "\n"
                    + segment["text"]
                    + "\n"
                )
        filename = "transcript.sbv"
        content = "\n".join(lines)

    elif export_type == "TTML":
        lines = generate_ttml(payload)
        for index, segment in enumerate(payload):
            if "verbatim_text" in segment.keys():
                lines.append(
                    "\t\t\t<p xml:id='subtitle"
                    + str(index + 1)
                    + "' begin='"
                    + segment["start_time"]
                    + "' end='"
                    + segment["end_time"]
                    + "' style='s1'>"
                    + segment["verbatim_text"].replace(",", "<br/>")
                    + "</p>"
                )
            else:
                lines.append(
                    "\t\t\t<p xml:id='subtitle"
                    + str(index + 1)
                    + "' begin='"
                    + segment["start_time"]
                    + "' end='"
                    + segment["end_time"]
                    + "' style='s1'>"
                    + segment["text"].replace(",", "<br/>")
                    + "</p>"
                )
        lines.append("\t\t</div>\n" + "\t</body>\n" + "</tt>\n")
        filename = "transcript.TTML"
        content = "\n".join(lines)

    elif export_type == "scc":
        filename = "transcript.scc"
        content = convert_scc_format(payload, task.task_type)

    elif export_type == "rt":
        lines = []
        content = convert_to_rt(payload, task.task_type)
        filename = "translation.rt"
    else:
        return Response(
            {"message": "This type is not supported."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if len(content) == 0:
        content = " "

    if return_file_content:
        response = HttpResponse(json.dumps(content), content_type="application/json")
        return response

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
    responses={200: "Returns all transcriptions for a particular video."},
)
@api_view(["GET"])
def retrieve_all_transcriptions(request):
    """
    Endpoint to retrieve all transcriptions for a given video ID
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

    # Get all transcripts for the video
    transcripts = Transcript.objects.filter(video_id=video_id)

    if not transcripts.exists():
        return Response(
            {"message": "No transcripts found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    transcript_list = []
    
    for transcript in transcripts:
        transcript_data = {
            "id": transcript.id,
            "status": transcript.status,
            "data": transcript.payload
        }
        transcript_list.append(transcript_data)

    return Response(
        {"transcripts": transcript_list},
        status=status.HTTP_200_OK,
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
    responses={200: "Returns all transcriptions for a particular video."},
)
@api_view(["GET"])
def retrieve_all_transcriptions(request):
    """
    Endpoint to retrieve all transcriptions for a given video ID
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
    # Get all transcripts for the video
    transcripts = Transcript.objects.filter(video_id=video_id)
    if not transcripts.exists():
        return Response(
            {"message": "No transcripts found."},
            status=status.HTTP_404_NOT_FOUND,
        )
    transcript_list = []
    for transcript in transcripts:
        transcript_data = {
            "id": transcript.id,
            "status": transcript.status,
            "transcript_type": transcript.transcript_type,
            "video": transcript.video.pk,
            "language": transcript.language,
            "task": transcript.task.pk,
            "user": (
                transcript.user.username if transcript.user else "No user associated"
            ),
            "parent_transcript": (
                transcript.parent_transcript.id
                if transcript.parent_transcript
                else "No parent transcript"
            ),
            "data": transcript.payload,
        }
        transcript_list.append(transcript_data)
    return Response(
        {"transcripts": transcript_list},
        status=status.HTTP_200_OK,
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
        task = (
            Task.objects.filter(video=video)
            .filter(task_type="TRANSCRIPTION_EDIT")
            .first()
        )
        transcript_obj = get_transcript_id(task)
        if transcript_obj is not None:
            transcript_payload = transcript_obj.payload
            data = {}
            data["payload"] = []
            for segment in transcript_payload["payload"]:
                if "text" in segment.keys() and len(segment["text"]) > 0:
                    data["payload"].append(segment)
            return Response(
                {"id": transcript_obj.id, "data": data},
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
        if task.status == "INPROGRESS" or task.status == "PARAPHRASE":
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
    responses={
        200: "Status has been changed successfully",
        400: "Bad request",
        404: "No transcript found for given task",
    },
)
@api_view(["GET"])
def reopen_completed_transcription_task(request):
    if not request.user.is_authenticated:
        return Response({"message":"You do not have enough permissions to access this view!"}, status=401)
    try:
        task_id = request.query_params.get("task_id")
    except KeyError:
        return Response(
            {
                "message": "Missing required parameter - task_id"
            },
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
    if transcript is not None:
        transcript_id = transcript.id
    try:
        transcript = Transcript.objects.get(pk=transcript_id)
        transcript.delete()
        task.status = "INPROGRESS"
        task.save()
        return Response(
            {
                "message": "Status has been changed successfully"
            },
            status=status.HTTP_200_OK,
        )
    except:
        return Response(
            {"message": "Transcript doesn't exist."},
            status=status.HTTP_400_BAD_REQUEST,
        )


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
    responses={
        200: "Status has been fetched successfully",
        400: "Bad request",
        404: "No transcript found for given task",
    },
)
@api_view(["GET"])
def fetch_transcript_status(request):
    if not request.user.is_authenticated:
        return Response({"message":"You do not have enough permissions to access this view!"}, status=401)
    try:
        task_id = request.query_params.get("task_id")
    except KeyError:
        return Response(
            {
                "message": "Missing required parameter - task_id"
            },
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
            {"message": "This task is not active yet."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    transcript = get_transcript_id(task)
    if transcript is not None:
        transcript_id = transcript.id
    try:
        transcript = Transcript.objects.get(pk=transcript_id)
        return Response(
            {
                "message": "Status has been fetched successfully",
                "task_id": task.id,
                "transcript_id": transcript_id,
                "status": transcript.status,
            },
            status=status.HTTP_200_OK,
        )
    except:
        return Response(
            {"message": "Transcript doesn't exist."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    
@swagger_auto_schema(
    method="post",
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        required=["task_id", "trs_status"],
        properties={
            "task_id": openapi.Schema(
                type=openapi.TYPE_INTEGER,
                description="An integer identifying the transcript instance",
            ),
            "trs_status": openapi.Schema(
                type=openapi.TYPE_STRING,
                description="Transcript task status to be set",
            )
        },
        description="Post request body",
    ),
    responses={
        200: "Status has been updated successfully",
        400: "Bad request",
        404: "No transcript found for given task",
    },
)
@api_view(["POST"])
def update_transcript_status(request):
    if not request.user.is_authenticated:
        return Response({"message":"You do not have enough permissions to access this view!"}, status=401)
    try:
        # Get the required data from the POST body
        task_id = request.data["task_id"]
        trs_status = request.data["trs_status"]
    except KeyError:
        return Response(
            {
                "message": "Missing required parameters - task_id or trs_status"
            },
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
            {"message": "This task is not active yet."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    transcript = get_transcript_id(task)
    if transcript is not None:
        transcript_id = transcript.id
    try:
        transcript = Transcript.objects.get(pk=transcript_id)
        if trs_status in ["TRANSCRIPTION_SELECT_SOURCE", "TRANSCRIPTION_EDITOR_ASSIGNED", "TRANSCRIPTION_EDIT_INPROGRESS", "TRANSCRIPTION_EDIT_COMPLETE", "TRANSCRIPTION_REVIEWER_ASSIGNED", "TRANSCRIPTION_REVIEW_INPROGRESS", "TRANSCRIPTION_REVIEW_COMPLETE"]:
            transcript.status = trs_status
            transcript.save()
            return Response(
                {
                    "message": "Status has been updated successfully",
                },
                status=status.HTTP_200_OK,
            )
        else:
            return Response(
                {"message": "Invalid Status"},
                status=status.HTTP_400_BAD_REQUEST,
            )
    except:
        return Response(
            {"message": "Transcript doesn't exist."},
            status=status.HTTP_400_BAD_REQUEST,
        )

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
        openapi.Parameter(
            "offset",
            openapi.IN_QUERY,
            description=("An integer to pass the offset"),
            type=openapi.TYPE_INTEGER,
            required=True,
        ),
        openapi.Parameter(
            "limit",
            openapi.IN_QUERY,
            description=("An integer to pass the limit"),
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
        page = request.query_params["offset"]
        limit = request.query_params["limit"]
    except KeyError:
        return Response(
            {"message": "Missing required parameters - task_id or offset or limit"},
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

    total_pages = math.ceil(len(transcript.payload["payload"]) / int(limit))
    if total_pages < int(page):
        page = 1
    start = (int(page) - 1) * int(limit)
    end = start + int(limit)
    page_records = transcript.payload["payload"][start:end]

    next_page = int(page) + 1
    pre_page = int(page) - 1

    if next_page > total_pages:
        end = len(transcript.payload["payload"])
        next_page = None

    if (pre_page <= 0) | (int(page) > total_pages):
        pre_page = None

    if len(page_records) == 0:
        return Response(
            {"payload": {"payload": []}, "source_type": transcript.transcript_type},
            status=status.HTTP_200_OK,
        )

    if "id" not in page_records[0].keys():
        for i in range(len(page_records)):
            page_records[i]["id"] = start + i

    if "speaker_id" not in transcript.payload["payload"][0]:
        for i in range(len(transcript.payload["payload"])):
            transcript.payload["payload"][i]["speaker_id"] = ""
        transcript.save()

    for segment in transcript.payload["payload"]:
        if "image_url" not in segment:
                segment["image_url"] = None

    count_empty = 0
    records = []
    for record_object in page_records:
        if "text" in record_object:
            records.append(record_object)
        else:
            count_empty += 1

    response = {"payload": records}

    return Response(
        {
            "payload": response,
            "source_type": transcript.transcript_type,
            "count": len(transcript.payload["payload"]),
            "current_count": len(records),
            "total_pages": total_pages,
            "current": int(page),
            "previous": pre_page,
            "next": next_page,
            "start": start + 1,
            "end": end,
        },
        status=status.HTTP_200_OK,
    )


import re


@swagger_auto_schema(
    method="post",
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        required=[
            "task_id",
            "word_to_replace",
            "replace_word",
            "transliteration_language",
            "replace_full_word",
        ],
        properties={
            "task_id": openapi.Schema(
                type=openapi.TYPE_INTEGER,
                description="An integer identifying the voice_over instance",
            ),
            "word_to_replace": openapi.Schema(
                type=openapi.TYPE_STRING,
                description="The word to replace ",
            ),
            "replace_word": openapi.Schema(
                type=openapi.TYPE_STRING,
                description="Replacement word ",
            ),
            "replace_full_word": openapi.Schema(
                type=openapi.TYPE_BOOLEAN,
                description="Replace full word",
            ),
            "transliteration_language": openapi.Schema(
                type=openapi.TYPE_STRING,
                description="Transliteration Language",
            ),
        },
        description="Post request body",
    ),
    responses={200: "Returns the updated transcript."},
)
@api_view(["POST"])
def replace_all_words(request):
    try:
        task_id = request.data["task_id"]
        word_to_replace = request.data["word_to_replace"]
        replace_word = request.data["replace_word"]
        replace_full_word = request.data["replace_full_word"]
        transliteration_language = request.data["transliteration_language"]

    except KeyError:
        return Response(
            {"message": "Missing required parameters."},
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

    # Replace all occurrences of word_to_replace with replace_word
    for record in transcript.payload["payload"]:
        if "text" in record:
            if replace_full_word:
                if transliteration_language == "en":
                    record["text"] = re.sub(
                        r"\b" + word_to_replace + r"\b", replace_word, record["text"]
                    )
                else:
                    record["text"] = record["text"].replace(
                        word_to_replace, replace_word
                    )
            else:
                record["text"] = record["text"].replace(word_to_replace, replace_word)

    # Save the updated transcript
    transcript.save()

    return Response(
        {"message": "Transcript updated successfully."},
        status=status.HTTP_200_OK,
    )


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
        openapi.Parameter(
            "time",
            openapi.IN_QUERY,
            description=("A string to pass the time"),
            type=openapi.TYPE_STRING,
            required=True,
        ),
        openapi.Parameter(
            "limit",
            openapi.IN_QUERY,
            description=("An integer to get the limit of payload"),
            type=openapi.TYPE_INTEGER,
            required=True,
        ),
    ],
    responses={200: "Returns the sentence after timeline dragging."},
)
@api_view(["GET"])
def get_sentence_from_timeline(request):
    task_id = request.query_params["task_id"]
    time = request.query_params["time"]
    limit = request.query_params["limit"]
    time = datetime.datetime.strptime(time, "%H:%M:%S.%f")
    unix_time = datetime.datetime.timestamp(time)

    try:
        task = Task.objects.get(pk=task_id)
    except Task.DoesNotExist:
        return Response(
            {"message": "Task doesn't exist."},
            status=status.HTTP_404_NOT_FOUND,
        )

    if not task.is_active:
        return Response(
            {"message": "This task is not active yet."},
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

    save_index = -1
    for ind, sentence in enumerate(transcript.payload["payload"]):
        if "start_time" not in sentence.keys():
            continue
        start_time = datetime.datetime.strptime(sentence["start_time"], "%H:%M:%S.%f")
        unix_start_time = datetime.datetime.timestamp(start_time)
        end_time = datetime.datetime.strptime(sentence["end_time"], "%H:%M:%S.%f")
        unix_end_time = datetime.datetime.timestamp(end_time)
        if unix_start_time <= unix_time and unix_end_time > unix_time:
            save_index = ind
            break
        if ind == 0:
            if unix_time < unix_start_time:
                save_index = ind
                break
        if (
            ind < len(transcript.payload["payload"]) - 1
            and type(transcript.payload["payload"][ind + 1]) == dict
            and "text" in transcript.payload["payload"][ind + 1].keys()
        ):
            end_time_of_next_sentence = datetime.datetime.strptime(
                transcript.payload["payload"][ind + 1]["start_time"], "%H:%M:%S.%f"
            )
            unix_end_time_of_next_sentence = datetime.datetime.timestamp(
                end_time_of_next_sentence
            )
            if (
                unix_end_time <= unix_time
                and unix_end_time_of_next_sentence > unix_time
            ):
                save_index = ind
                break

    if save_index == -1:
        save_index = 0
    length_payload = len(transcript.payload["payload"])
    sentence_offset = math.ceil((save_index + 1) / int(limit))
    response = get_payload_request(request, task_id, limit, sentence_offset)
    return Response(
        response.data,
        status=status.HTTP_200_OK,
    )


def get_payload_request(request, task_id, limit, offset):
    new_request = HttpRequest()
    new_request.method = "GET"
    new_request.task_id = task_id
    new_request.limit = limit
    new_request.offset = offset
    new_request.GET = request.GET.copy()
    new_request.GET["task_id"] = task_id
    new_request.GET["limit"] = limit
    new_request.GET["offset"] = offset
    return get_payload(new_request)


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
def get_full_payload(request):
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

    count = 0
    for sentence in transcript.payload["payload"]:
        sentence["id"] = count
        count = count + 1

    return Response(
        {"payload": transcript.payload, "source_type": transcript.transcript_type},
        status=status.HTTP_200_OK,
    )


def send_mail_to_user(task):
    try:
        if task.user.enable_mail:
            if task.eta is not None:
                try:
                    task_eta = str(task.eta.strftime("%Y-%m-%d"))
                except:
                    task_eta = str(task.eta)
            else:
                task_eta = "-"
            logging.info("Send email to user %s", task.user.email)

            # Improved table HTML with width control and text wrapping
            table_to_send = """<p>
            <head>
            <style>
            table { 
                border: 1px solid black; 
                border-collapse: collapse; 
                width: 600px; 
                table-layout: fixed;
            }
            th, td { 
                border: 1px solid black; 
                word-wrap: break-word; 
                padding: 8px; 
                vertical-align: top;
                max-width: 200px;
            }
            </style>
            </head>
            <body>
            <table>"""

            data = """<tr><th>Video Name</th><td>{name}</td></tr>
                <tr><th>Video URL</th><td>{url}</td></tr>
                <tr><th>Project Name</th><td>{project_name}</td></tr>
                <tr><th>ETA</th><td>{eta}</td></tr>
                <tr><th>Description</th><td>{description}</td></tr>
                </table></body></p>""".format(
                name=task.video.name,
                url=task.video.url,
                project_name=task.video.project_id.title,
                eta=task_eta,
                description=task.description,
            )
            final_table = table_to_send + data
            email = EmailMultiAlternatives(
            subject=f"Task ID {task.id} - {task.get_task_type_label} is active",
            body=f"Dear User,\n\nFollowing task is active.\nTask ID: {task.id}\n\nPlease see the details below.",
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[task.user.email],
        )

            email.attach_alternative(final_table, "text/html")
            email.send()
        else:
            logging.info("Email is not enabled %s", task.user.email)
    except Exception as e:
        logging.error("Error in send_mail_to_user: %s", str(e))


def check_if_transcription_correct(transcription_obj, task):
    bad_sentences = get_bad_sentences_in_progress_for_transcription(
        transcription_obj, task
    )
    if len(bad_sentences) > 0:
        transcription = (
            Transcript.objects.filter(video=task.video)
            .filter(status="TRANSCRIPTION_EDIT_INPROGRESS")
            .first()
        )
        if transcription is not None:
            transcription_obj.status = "TRANSCRIPTION_EDIT_INPROGRESS"
            transcription_obj.parent_transcript = transcription.parent_transcript
            transcription_obj.save()
            transcription.parent_transcript = None
            transcription.save()
            transcription.delete()
            task.status = "INPROGRESS"
            task.save()
        else:
            transcription = (
                Transcript.objects.filter(video=task.video)
                .filter(status="TRANSCRIPTION_SELECT_SOURCE")
                .first()
            )
            transcription_obj.parent_transcript = None
            transcription_obj.status = "TRANSCRIPTION_SELECT_SOURCE"
            transcription_obj.save()
            task.status = "SELECTED_SOURCE"
            transcription.delete()
            task.save()
        response = {
            "data": bad_sentences,
            "message": "Transcription task couldn't be completed. Please correct the following sentences.",
        }
        return response
    return None


def change_active_status_of_next_tasks(task, transcript_obj):
    tasks = Task.objects.filter(video=task.video)
    activate_translations = True

    # change status of transcript object to inprogress again and call function to generate initial paraphrasing with the payload
    # Handle failure by updating task status to fail and post process while working (if celery)

    if (
        "EDIT" in task.task_type
        and tasks.filter(task_type="TRANSCRIPTION_REVIEW").first()
    ):
        activate_translations = False
        tasks.filter(task_type="TRANSCRIPTION_REVIEW").update(is_active=True)
        for task in tasks.filter(task_type="TRANSCRIPTION_REVIEW"):
            send_mail_to_user(task)
        transcript = (
            Transcript.objects.filter(video=task.video)
            .filter(status="TRANSCRIPTION_REVIEWER_ASSIGNED")
            .first()
        )

        if transcript is not None:
            transcript.parent_transcript = transcript_obj
            transcript.payload = transcript_obj.payload
            transcript.save()

    if tasks.filter(task_type="TRANSLATION_VOICEOVER_EDIT").first():
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
                translation.transcript = transcript_obj
                translation.save()
                if source_type == None or source_type == "MACHINE_GENERATED":
                    source_type = "MACHINE_GENERATED"
                    celery_nmt_tts_call.delay(task_id=translation.task.id)
                else:
                    payloads = generate_translation_payload(
                        transcript_obj,
                        translation.target_language,
                        [source_type],
                        translation.task.user.id,
                    )
                    translation.payload = payloads[source_type]
                    translation.save()

    if activate_translations and tasks.filter(task_type="TRANSLATION_EDIT").first():
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
                translation.transcript = transcript_obj
                translation.save()
                if source_type == None or source_type == "MACHINE_GENERATED":
                    source_type = "MACHINE_GENERATED"
                    translation.transcript = transcript_obj
                    translation.save()
                    celery_nmt_call.delay(task_id=translation.task.id)
                else:
                    payloads = generate_translation_payload(
                        transcript,
                        target_language,
                        [source_type],
                        translation.task.user.id,
                    )
                    translation.payload = payloads[source_type]
                    translation.save()
    else:
        print("No change in status")


# Helper function to call the paraphrasing API
def paraphrase_text(text):
    # Set API configuration
    try:
        text = get_model_output(user_prompt=text)
    except:
        True
    return text


def update_transcript_paraphrases(transcript):
    for entry in transcript.payload["payload"]:
        if "text" in entry and entry["text"]:
            entry["paraphrased_text"] = paraphrase_text(entry["text"])
        else:
            entry["paraphrased_text"] = None
    transcript.paraphrase_stage = True
    transcript.save()
    task = transcript.task
    task.status = "PARAPHRASE"
    task.save()


# Helper function to update the transcript
def update_transcript(i, start_offset, payload, transcript):
    paraphrased_text = payload["payload"][i].get("paraphrased_text")
    if payload["payload"][i].get("paraphrase"):
        paraphrased_text = paraphrase_text(payload["payload"][i]["text"])

    transcript.payload["payload"][start_offset + i] = {
        "start_time": payload["payload"][i]["start_time"],
        "end_time": payload["payload"][i]["end_time"],
        "text": payload["payload"][i]["text"],
        "speaker_id": payload["payload"][i]["speaker_id"],
        "paraphrased_text": paraphrased_text,
        "image_url": payload["payload"][i].get("image_url")
    }


def modify_payload(offset, limit, payload, start_offset, end_offset, transcript):
    count_sentences = len(transcript.payload["payload"])
    total_pages = math.ceil(len(transcript.payload["payload"]) / int(limit))
    if (
        offset != total_pages
        and type(payload) == dict
        and "payload" in payload.keys()
        and len(payload["payload"]) == 0
    ):
        return

    if len(payload["payload"]) == limit:
        logging.info(
            "Limit is equal to length of payload %s", str(len(payload["payload"]))
        )
        length = len(payload["payload"])
        length_2 = -1
        if end_offset > count_sentences:
            length_2 = end_offset - count_sentences
            length = length - length_2
        for i in range(length):
            if "text" in payload["payload"][i].keys():
                update_transcript(i, start_offset, payload, transcript)
            else:
                logging.info("Text missing in payload")
        if length_2 > 0:
            for i in range(length_2):
                if "text" in payload["payload"][i].keys():
                    print("Modifying payload")
                    transcript.payload["payload"].insert(
                        start_offset + i + length,
                        {
                            "start_time": payload["payload"][length + i]["start_time"],
                            "end_time": payload["payload"][length + i]["end_time"],
                            "text": payload["payload"][length + i]["text"],
                            "speaker_id": payload["payload"][i]["speaker_id"],
                            "paraphrased_text": (
                                paraphrase_text(payload["payload"][length + i]["text"])
                                if payload["payload"][i].get("paraphrase")
                                else payload["payload"][length + i].get(
                                    "paraphrased_text"
                                )
                            ),  # Generate paraphrased text if paraphrase=true
                            "image_url": payload["payload"][i].get("image_url"),
                        },
                    )
                else:
                    logging.info("Text missing in payload")
    elif len(payload["payload"]) < limit:
        logging.info(
            "Limit is less than length of payload, %s", str(len(payload["payload"]))
        )
        length = len(payload["payload"])
        length_2 = -1
        length_3 = -1
        if end_offset > count_sentences:
            if length > len(transcript.payload["payload"][start_offset:end_offset]):
                length_2 = length - len(
                    transcript.payload["payload"][start_offset:end_offset]
                )
                length = length - length_2
                logging.info(
                    "Length of payload {}, end_offset {}, count of sentences {}, after splitting {}".format(
                        str(length),
                        str(end_offset),
                        str(count_sentences),
                        str(length_2),
                    )
                )
            else:
                length_3 = (
                    len(transcript.payload["payload"][start_offset:end_offset]) - length
                )
                logging.info(
                    "Length of payload {}, end_offset {}, count of sentences {}, after merging {}".format(
                        str(length),
                        str(end_offset),
                        str(count_sentences),
                        str(length_3),
                    )
                )
            for i in range(length):
                if "text" in payload["payload"][i].keys():
                    update_transcript(i, start_offset, payload, transcript)
                else:
                    logging.info("Text missing in payload")
            if length_2 > 0:
                for i in range(length_2):
                    if "text" in payload["payload"][i].keys():
                        transcript.payload["payload"].insert(
                            start_offset + i + length,
                            {
                                "start_time": payload["payload"][length + i][
                                    "start_time"
                                ],
                                "end_time": payload["payload"][length + i]["end_time"],
                                "text": payload["payload"][length + i]["text"],
                                "speaker_id": payload["payload"][length + i][
                                    "speaker_id"
                                ],
                                "paraphrased_text": (
                                    paraphrase_text(
                                        payload["payload"][length + i]["text"]
                                    )
                                    if payload["payload"][i].get("paraphrase")
                                    else payload["payload"][length + i].get(
                                        "paraphrased_text"
                                    )
                                ),  # Generate paraphrased text if paraphrase=true
                                "image_url": payload["payload"][i].get("image_url"),
                            },
                        )
                    else:
                        logging.info("Text missing in payload")
            if length_3 > 0:
                for i in range(length_3):
                    transcript.payload["payload"][start_offset + i + length] = {}
        else:
            logging.info("length of payload %s", str(length))
            for i in range(length):
                if "text" in payload["payload"][i].keys():
                    update_transcript(i, start_offset, payload, transcript)
                else:
                    logging.info("Text missing in payload")
            delete_indices = []
            logging.info(
                "length exceeds limit by limit - length %s", str(limit - length)
            )
            for i in range(limit - length):
                delete_indices.append(start_offset + i + length)

            logging.info("delete_indices %s", str(delete_indices))
            for ind in delete_indices:
                transcript.payload["payload"][ind] = {}
    else:
        logging.info("Limit is greater than length of payload")
        if end_offset > count_sentences:
            length = count_sentences - start_offset
            length_2 = len(payload["payload"]) - length
            insert_at = start_offset + length
        else:
            length = limit
            length_2 = len(payload["payload"]) - limit
            insert_at = start_offset + length
        for i in range(length):
            if "text" in payload["payload"][i].keys():
                update_transcript(i, start_offset, payload, transcript)
            else:
                logging.info("Text missing in payload")
        for i in range(length_2):
            if "text" in payload["payload"][i].keys():
                transcript.payload["payload"].insert(
                    insert_at + i,
                    {
                        "start_time": payload["payload"][length + i]["start_time"],
                        "end_time": payload["payload"][length + i]["end_time"],
                        "text": payload["payload"][length + i]["text"],
                        "speaker_id": payload["payload"][length + i]["speaker_id"],
                        "paraphrased_text": (
                            paraphrase_text(payload["payload"][length + i]["text"])
                            if payload["payload"][i].get("paraphrase")
                            else payload["payload"][length + i].get("paraphrased_text")
                        ),  # Generate paraphrased text if paraphrase=true
                        "image_url": payload["payload"][i].get("image_url"),
                    },
                )
        # last_valid_end_time = transcript.payload["payload"][len(payload["payload"])][
        #     "end_time"
        # ]
        offset_to_check = start_offset + len(payload["payload"])
        last_valid_start_time = transcript.payload["payload"][offset_to_check - 1][
            "start_time"
        ]
        delete_indices = []
        for i in range(offset_to_check, offset_to_check + 50):
            if (
                i < len(transcript.payload["payload"])
                and "start_time" in transcript.payload["payload"][i].keys()
                and last_valid_start_time
                >= transcript.payload["payload"][i]["start_time"]
            ):
                delete_indices.append(i)
                transcript.payload["payload"][i] = {}
            else:
                break
        delete_indices.reverse()
        for ind in delete_indices:
            transcript.payload["payload"].pop(ind)

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
                description="A boolean to complete the task",
            ),
        },
        description="Post request body for projects which have save_type == new_record",
    ),
    responses={
        200: "Transcript has been saved successfully",
    },
)
@api_view(["POST"])
def save_full_transcription(request):
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
                    print("Transcript saved")
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
                        task.status = "INPROGRESS"
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
                        # "data": transcript_obj.payload,
                        "message": "Transcript is submitted.",
                    },
                    status=status.HTTP_200_OK,
                )
            else:
                return Response(
                    {
                        "task_id": task_id,
                        "transcript_id": transcript_obj.id,
                        # "data": transcript_obj.payload,
                        "message": "Saved as draft.",
                    },
                    status=status.HTTP_200_OK,
                )

    except Transcript.DoesNotExist:
        return Response(
            {"message": "Transcript doesn't exist."},
            status=status.HTTP_400_BAD_REQUEST,
        )


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
                description="A boolean to complete the task",
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
        offset = request.data["offset"]
        limit = request.data["limit"]

    except KeyError:
        return Response(
            {
                "message": "Missing required parameters - payload or task_id or offset or limit"
            },
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
            {"message": "This task is not active yet."},
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
    bookmarked_segment = request.data.get("bookmark", None)
    user = request.user
    if bookmarked_segment is not None:
        user.user_history = {
            "task_id": task_id,
            "offset": offset,
            "task_type": task.task_type,
            "segment": bookmarked_segment,
        }
        user.save()
    start_offset = (int(offset) - 1) * int(limit)
    end_offset = start_offset + int(limit)
    # Retrieve the transcript object
    try:
        transcript = Transcript.objects.get(pk=transcript_id)
        if (
            type(payload) != dict
            or "payload" not in payload.keys()
            or len(payload["payload"]) == 0
            or "text" not in payload["payload"][0].keys()
        ):
            return Response(
                {"message": "Invalid Transcript."}, status=status.HTTP_400_BAD_REQUEST
            )
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
                        task.video.project_id.paraphrasing_enabled
                        and transcript.paraphrase_stage != True
                    ):
                        transcript_obj = (
                            Transcript.objects.filter(status=TRANSCRIPTION_EDIT_INPROGRESS)
                            .filter(video=task.video)
                            .first()
                        )

                        tc_status = TRANSCRIPTION_EDIT_INPROGRESS
                        if transcript_obj is not None:
                            modify_payload(
                                offset,
                                limit,
                                payload,
                                start_offset,
                                end_offset,
                                transcript_obj,
                            )
                            # transcript_obj.payload = payload
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
                                payload=transcript_obj.payload,
                                user=request.user,
                                task=task,
                                status=tc_status,
                            )
                            modify_payload(
                                offset,
                                limit,
                                payload,
                                start_offset,
                                end_offset,
                                transcript_obj,
                            )
                            transcript_obj.save()
                        task.status = "POST PROCESS"
                        task.save()
                        update_transcript_paraphrases(transcript_obj)
                    else:
                        if (
                            Transcript.objects.filter(
                                status=TRANSCRIPTION_EDIT_COMPLETE
                            )
                            .filter(video=task.video)
                            .first()
                            is not None
                        ):
                            if task.status == "INPROGRESS":
                                task.status = "COMPLETE"
                                task.save()
                            if task.status == "SELECTED_SOURCE":
                                task.status = "COMPLETE"
                                task.save()
                            if task.status == "PARAPHRASE":
                                task.status = "COMPLETE"
                                task.save()
                            return Response(
                                {
                                    "message": "Final Edited Transcript already submitted."
                                },
                                status=status.HTTP_201_CREATED,
                            )
                        tc_status = TRANSCRIPTION_EDIT_COMPLETE
                        transcript_type = transcript.transcript_type
                        transcript_obj = Transcript.objects.create(
                            transcript_type=transcript_type,
                            parent_transcript=transcript,
                            video=transcript.video,
                            language=transcript.language,
                            payload=transcript.payload,
                            user=request.user,
                            task=task,
                            status=tc_status,
                        )
                        modify_payload(
                            offset,
                            limit,
                            payload,
                            start_offset,
                            end_offset,
                            transcript_obj,
                        )
                        for item in transcript_obj.payload["payload"]:
                            try:
                                item['verbatim_text'] = item['text']
                                item['text'] = item['paraphrased_text'] if 'paraphrased_text' in item and item['paraphrased_text'] not in [None, ""] else item['verbatim_text']
                            except:
                                True
                        transcript_obj.save()
                        task.status = "COMPLETE"
                        task.save()
                        response = check_if_transcription_correct(transcript_obj, task)
                        if type(response) == dict:
                            return Response(
                                {
                                    "data": response["data"],
                                    "message": response["message"],
                                },
                                status=status.HTTP_400_BAD_REQUEST,
                            )

                        delete_indices = []
                        for index, sentence in enumerate(
                            transcript_obj.payload["payload"]
                        ):
                            if "text" not in sentence.keys():
                                delete_indices.append(index)

                        delete_indices.reverse()
                        for ind in delete_indices:
                            transcript_obj.payload["payload"].pop(ind)
                        transcript_obj.save()
                        change_active_status_of_next_tasks(task, transcript_obj)
                else:
                    transcript_obj = (
                        Transcript.objects.filter(status=TRANSCRIPTION_EDIT_INPROGRESS)
                        .filter(video=task.video)
                        .first()
                    )

                    tc_status = TRANSCRIPTION_EDIT_INPROGRESS
                    if transcript_obj is not None:
                        modify_payload(
                            offset,
                            limit,
                            payload,
                            start_offset,
                            end_offset,
                            transcript_obj,
                        )
                        # transcript_obj.payload = payload
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
                            payload=transcript_obj.payload,
                            user=request.user,
                            task=task,
                            status=tc_status,
                        )
                        modify_payload(
                            offset,
                            limit,
                            payload,
                            start_offset,
                            end_offset,
                            transcript_obj,
                        )
                        transcript_obj.save()
                        task.status = "INPROGRESS"
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
                            payload=transcript.payload,
                            user=request.user,
                            task=task,
                            status=tc_status,
                        )
                        modify_payload(
                            offset,
                            limit,
                            payload,
                            start_offset,
                            end_offset,
                            transcript_obj,
                        )
                        for item in transcript_obj.payload["payload"]:
                            item['verbatim_text'] = item['text']
                            item['text'] = item['paraphrased_text'] if 'paraphrased_text' in item and item['paraphrased_text'] not in [None, ""] else item['verbatim_text']
                        task.completed = {
                            "user_id": request.user.id,
                            "timestamp": now().isoformat(),
                           
                        }
                        transcript_obj.save()
                        task.status = "COMPLETE"
                        task.save()
                        response = check_if_transcription_correct(transcript_obj, task)
                        if type(response) == dict:
                            return Response(
                                {
                                    "data": response["data"],
                                    "message": response["message"],
                                },
                                status=status.HTTP_400_BAD_REQUEST,
                            )

                        delete_indices = []
                        for index, sentence in enumerate(
                            transcript_obj.payload["payload"]
                        ):
                            if "text" not in sentence.keys():
                                delete_indices.append(index)

                        delete_indices.reverse()
                        for ind in delete_indices:
                            transcript_obj.payload["payload"].pop(ind)
                        transcript_obj.save()
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
                        modify_payload(
                            offset,
                            limit,
                            payload,
                            start_offset,
                            end_offset,
                            transcript_obj,
                        )
                        # transcript_obj.payload = payload
                        transcript_obj.transcript_type = transcript_type
                        transcript_obj.save()
                    else:
                        transcript_obj = Transcript.objects.create(
                            transcript_type=transcript_type,
                            parent_transcript=transcript,
                            video=transcript.video,
                            language=transcript.language,
                            payload=transcript.payload,
                            user=request.user,
                            task=task,
                            status=tc_status,
                        )
                        modify_payload(
                            offset,
                            limit,
                            payload,
                            start_offset,
                            end_offset,
                            transcript_obj,
                        )
                        transcript_obj.save()
                        task.status = "INPROGRESS"
                        task.save()

            if request.data.get("final"):
                if transcript_obj.payload != "" and transcript_obj.payload is not None:
                    num_words = 0
                    index = -1
                    for idv_transcription in transcript_obj.payload["payload"]:
                        index += 1
                        if "text" in idv_transcription.keys():
                            cleaned_text = regex.sub(
                                r"[^\p{L}\s]", "", idv_transcription["text"]
                            ).lower()  # for removing special characters
                            cleaned_text = regex.sub(
                                r"\s+", " ", cleaned_text
                            )  # for removing multiple blank spaces
                            num_words += len(cleaned_text.split(" "))
                            transcript_obj.payload["payload"][index][
                                "start_time"
                            ] = format_timestamp(
                                transcript_obj.payload["payload"][index]["start_time"]
                            )
                            transcript_obj.payload["payload"][index][
                                "end_time"
                            ] = format_timestamp(
                                transcript_obj.payload["payload"][index]["end_time"]
                            )
                    transcript_obj.payload["word_count"] = num_words
                    transcript_obj.save()
                # celery_align_json.delay(transcript_obj.id)
                return Response(
                    {
                        "task_id": task_id,
                        "transcript_id": transcript_obj.id,
                        # "data": transcript_obj.payload,
                        "message": "Transcript is submitted.",
                    },
                    status=status.HTTP_200_OK,
                )
            else:
                return Response(
                    {
                        "task_id": task_id,
                        "transcript_id": transcript_obj.id,
                        # "data": transcript_obj.payload,
                        "message": "Saved as draft.",
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
    return Response(
        {"message": "Soemthing went wrong!"},
        status=status.HTTP_400_BAD_REQUEST,
    )
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
    elif (
        transcript.filter(status="TRANSCRIPTION_REVIEWER_ASSIGNED")
        .filter(task__is_active=True)
        .first()
        != None
    ):
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
        data = align_json_api(transcript_obj)
        for i in range(len(transcript_obj.payload["payload"])):
            if "text" in transcript_obj.payload["payload"][i].keys():
                data[str(i + 1)]["start_time"] = transcript_obj.payload["payload"][i][
                    "start_time"
                ]
                data[str(i + 1)]["end_time"] = transcript_obj.payload["payload"][i][
                    "end_time"
                ]

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
@authentication_classes([])
@permission_classes([])
def get_transcription_supported_languages(request):
    """
    Endpoint to get the supported languages for ASR API
    """
    return Response(
        [
            {"label": label, "value": value}
            for label, value in TRANSCRIPTION_SUPPORTED_LANGUAGES.items()
        ],
        status=status.HTTP_200_OK,
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


@api_view(["GET"])
@authentication_classes([])
@permission_classes([])
def get_transcription_report(request):
    start_date_str = request.query_params.get("start_date")
    end_date_str = request.query_params.get("end_date")

    transcripts = Transcript.objects.filter(status="TRANSCRIPTION_EDIT_COMPLETE")

    def parse_date(date_str):
        year, month, day = map(int, date_str.split("-"))
        return timezone.make_aware(datetime.datetime(year, month, day, 0, 0, 0))

    if start_date_str and end_date_str:
        start_date = parse_date(start_date_str)
        end_date = parse_date(end_date_str) + timedelta(days=1)
        transcripts = transcripts.filter(
            updated_at__date__range=(start_date.date(), end_date.date())
        )

    transcripts = transcripts.exclude(
        video__project_id__organization_id__title__isnull=True
    ).values(
        "language",
        "video__project_id__organization_id__title",
        "video__project_id__organization_id__is_active", 
    )
    transcription_statistics = transcripts.annotate(
        total_duration=Sum(F("video__duration"))
    ).order_by("-total_duration")
    transcript_data = []
    for elem in transcription_statistics:
        transcript_dict = {
            "org": {
                "name": elem["video__project_id__organization_id__title"],
                "is_active": elem["video__project_id__organization_id__is_active"],
            },
            "language": {
                "value": dict(TRANSCRIPTION_LANGUAGE_CHOICES)[elem["language"]],
                "label": "Media Language",
            },
            "total_duration": {
                "value": round(elem["total_duration"].total_seconds() / 3600, 3),
                "label": "Transcripted Duration (Hours)",
            },
            "transcripts_completed": {
                "value": len(
                    transcripts.filter(language=elem["language"]).filter(
                        video__project_id__organization_id__title=elem[
                            "video__project_id__organization_id__title"
                        ]
                    )
                ),
                "label": "Transcription Tasks Count",
            },
        }
        transcript_data.append(transcript_dict)

    transcript_data.sort(key=lambda x: x["org"]["name"])

    res = []
    for org, items in groupby(transcript_data, key=lambda x: x["org"]["name"]):
        lang_data = []
        is_active_status = None
        for i in items:
            is_active_status = i["org"]["is_active"]  
            del i["org"]
            lang_data.append(i)
        temp_data = {"org": {"name": org, "is_active": is_active_status}, "data": lang_data}
        res.append(temp_data)

    return Response(res, status=status.HTTP_200_OK)


@swagger_auto_schema(
    method="post",
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        required=["task_ids"],
        properties={
            "task_ids": openapi.Schema(
                type=openapi.TYPE_OBJECT,
                description="An integer identifying the task instance",
            ),
        },
    ),
    responses={200: "Generates the YTT and store in azure"},
)
@api_view(["POST"])
def generate_ytt_for_transcript(request):
    task_ids = request.data["task_ids"]
    for task_id in task_ids:
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
        if task.status == "COMPLETE":
            if (
                transcript.payload != None
                and "payload" in transcript.payload.keys()
                and len(transcript.payload["payload"]) > 0
                and "ytt_azure_url" in transcript.payload.keys()
            ):
                file_location = transcript.payload["ytt_azure_url"].split("/")[-1]
                download_ytt_from_azure(file_location)
            else:
                try:
                    data = align_json_api(transcript)
                    time_now = datetime.datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
                    file_location = (
                        "{}_Video_{}_{}".format(app_name, transcript.video.id, time_now)
                        + ".ytt"
                    )
                    ytt_genorator(data, file_location, prev_line_in=0, mode="data")
                    upload_ytt_to_azure(transcript, file_location)
                    os.remove(file_location)
                except:
                    logging.info("Error in exporting to ytt format %s", str(task_id))
                    return Response(
                        {"message": "Error in exporting to ytt format"},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    )
    return Response({"message": "All the ytt are aligned"}, status=status.HTTP_200_OK)


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
