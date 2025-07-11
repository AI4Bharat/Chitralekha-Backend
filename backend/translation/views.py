import datetime
from io import StringIO
import webvtt
from django.shortcuts import get_object_or_404
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import status
from rest_framework.decorators import (
    api_view,
    permission_classes,
    authentication_classes,
)
from django.utils import timezone
from datetime import timedelta
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from transcript.utils.TTML import generate_ttml
from transcript.models import Transcript
from video.models import Video
from task.models import Task, TRANSLATION_VOICEOVER_EDIT, COMPLETE
from rest_framework.decorators import action
from django.http import HttpResponse
from django.http import HttpRequest
from django.core.files.base import ContentFile
import requests
from .metadata import TRANSLATION_SUPPORTED_LANGUAGES, TRANSLATION_LANGUAGE_CHOICES
from transcript.utils.TTML import generate_ttml
from .models import (
    Translation,
    MACHINE_GENERATED,
    UPDATED_MACHINE_GENERATED,
    MANUALLY_CREATED,
    UPDATED_MANUALLY_CREATED,
    TRANSLATION_TYPE_CHOICES,
    TRANSLATION_SELECT_SOURCE,
    TRANSLATION_EDITOR_ASSIGNED,
    TRANSLATION_EDIT_INPROGRESS,
    TRANSLATION_EDIT_COMPLETE,
    TRANSLATION_REVIEWER_ASSIGNED,
    TRANSLATION_REVIEW_INPROGRESS,
    TRANSLATION_REVIEW_COMPLETE,
)
from voiceover.utils import process_translation_payload, get_bad_sentences_in_progress
from .decorators import is_translation_editor
from .serializers import TranslationSerializer
from .utils import (
    get_batch_translations_using_indictrans_nmt_api,
    convert_to_paragraph,
    convert_to_paragraph_monolingual,
    convert_to_paragraph_bilingual,
    convert_to_rt,
    convert_scc_format,
    generate_translation_payload,
    set_fail_for_translation_task,
)
from django.db.models import Q, Count, Avg, F, FloatField, BigIntegerField, Sum
from django.db.models.functions import Cast
from operator import itemgetter
from itertools import groupby
from voiceover.models import VoiceOver
from project.models import Project
import config
from task.tasks import celery_tts_call
import logging
import datetime
import math
import json
import regex
import requests
from transcript.utils.timestamp import *
from django.core.mail import EmailMultiAlternatives
from django.conf import settings
from transcript.views import get_transcript_id
from task.tasks import celery_nmt_tts_call
from django.utils.timezone import now

@api_view(["GET"])
def get_translation_export_types(request):
    return Response(
        {
            "export_types": [
                "srt",
                "vtt",
                "txt",
                "docx",
                "docx-bilingual",
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
            description=(
                "export type parameter srt/vtt/txt/docx/docx-bilingual/sbv/TTML/scc/rt"
            ),
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
    responses={200: "Translation has been exported."},
)
@api_view(["GET"])
def export_translation(request):
    task_id = request.query_params.get("task_id")
    export_type = request.query_params.get("export_type")
    return_file_content = request.query_params.get("return_file_content")
    with_speaker_info = request.query_params.get("with_speaker_info", "false")

    with_speaker_info = with_speaker_info.lower() == "true"
    if task_id is None or export_type is None:
        return Response(
            {"message": "missing param : task_id or export_type"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        task = Task.objects.get(pk=task_id)
    except Task.DoesNotExist:
        return Response(
            {"message": "Task not found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    translation = get_translation_id(task)
    if translation is None:
        return Response(
            {"message": "Translation doesn't exist."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if task.task_type == TRANSLATION_VOICEOVER_EDIT and task.status != COMPLETE:
        voice_over_obj = VoiceOver.objects.filter(task=task).first()

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
                "target_text": segment["text"],
                "speaker_id": "",
                "unix_start_time": unix_start_time,
                "unix_end_time": unix_end_time,
                "text": segment["transcription_text"],
                "image_url": segment.get("image_url"),
            }
            updated_payload.append(updated_segment)
        translation.payload["payload"] = updated_payload
        translation.save()

    payload = translation.payload["payload"]
    if with_speaker_info:
        speaker_info = translation.payload.get("speaker_info", None)
        if speaker_info == None:
            return Response(
                {"message": "There is no speaker info in this translation."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        speaker_info_dict = {
            speaker["label"]: speaker["value"] for speaker in speaker_info
        }

    supported_types = [
        "srt",
        "vtt",
        "txt",
        "docx",
        "docx-bilingual",
        "scc",
        "sbv",
        "TTML",
        "rt",
    ]
    if export_type not in supported_types:
        return Response(
            {
                "message": "exported type only supported formats are : {srt, vtt, txt, docx, docx-bilingual, sbv, TTML, scc, rt}"
            },
            status=status.HTTP_404_NOT_FOUND,
        )

    lines = []
    if export_type == "srt":
        for index, segment in enumerate(payload):
            if "text" in segment.keys():
                lines.append(str(index + 1))
                lines.append(segment["start_time"] + " --> " + segment["end_time"])
                if len(segment.get("speaker_id", "")) > 0 and with_speaker_info:
                    lines.append(
                        speaker_info_dict[segment["speaker_id"]]
                        + ": "
                        + segment["target_text"]
                        + "\n"
                    )
                else:
                    lines.append(segment["target_text"] + "\n")
        filename = "translation.srt"
        content = "\n".join(lines)
    elif export_type == "vtt":
        lines.append("WEBVTT\n")
        for index, segment in enumerate(payload):
            if "text" in segment.keys():
                lines.append(str(index + 1))
                lines.append(segment["start_time"] + " --> " + segment["end_time"])
                if len(segment.get("speaker_id", "")) > 0 and with_speaker_info:
                    lines.append(
                        speaker_info_dict[segment["speaker_id"]]
                        + ": "
                        + segment["target_text"]
                        + "\n"
                    )
                else:
                    lines.append(segment["target_text"] + "\n")
        filename = "translation.vtt"
        content = "\n".join(lines)
    elif export_type == "txt":
        for index, segment in enumerate(payload):
            if "text" in segment.keys():
                lines.append(segment["target_text"])
        filename = "translation.txt"
        content = convert_to_paragraph(lines, task.video.name)
    elif export_type == "docx":
        filename = "translation.docx"
        content = convert_to_paragraph_monolingual(payload, task.video.name, task_id)
        return content
    elif export_type == "docx-bilingual":
        filename = "translation.docx"
        content = convert_to_paragraph_bilingual(payload, task.video.name, task_id)
        return content

    elif export_type == "sbv":
        for index, segment in enumerate(payload):
            lines.append(
                segment["start_time"]
                + ","
                + segment["end_time"]
                + "\n"
                + segment["target_text"]
                + "\n"
            )
        filename = "translation.sbv"
        content = "\n".join(lines)

    elif export_type == "TTML":
        lines = generate_ttml(payload)
        for index, segment in enumerate(payload):
            lines.append(
                "\t\t\t<p xml:id='subtitle"
                + str(index + 1)
                + "' begin='"
                + segment["start_time"]
                + "' end='"
                + segment["end_time"]
                + "' style='s1'>"
                + segment["target_text"].replace(",", "<br/>")
                + "</p>"
            )
        lines.append("\t\t</div>\n" + "\t</body>\n" + "</tt>\n")
        filename = "translation.TTML"
        content = "\n".join(lines)

    elif export_type == "scc":
        content = convert_scc_format(payload, task.task_type)
        filename = "translation.scc"
    elif export_type == "rt":
        lines = []
        content = convert_to_rt(payload, task.task_type)
        filename = "translation.rt"

    else:
        return Response(
            {"message": "This type is not supported."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    content_type = "application/json"
    if len(content) == 0:
        content = " "
    if return_file_content:
        response = HttpResponse(json.dumps(content), content_type="application/json")
        return response

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
            "target_language",
            openapi.IN_QUERY,
            description=("An integer to pass the video id"),
            type=openapi.TYPE_STRING,
            required=True,
        ),
    ],
    responses={200: "Returns the translation for a particular video and language"},
)
@api_view(["GET"])
def retrieve_translation(request):
    """
    Endpoint to retrive a translation for a translation entry
    """

    # Check if video_id and language and transcript_type has been passed
    if "video_id" not in dict(request.query_params) or "target_language" not in dict(
        request.query_params
    ):
        return Response(
            {"message": "missing param : video_id or target_language"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    video_id = request.query_params["video_id"]
    target_language = request.query_params["target_language"]
    user_id = request.user.id

    try:
        video = Video.objects.get(pk=video_id)
    except Video.DoesNotExist:
        return Response(
            {"message": "Video not found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    # Get the latest transcript
    translation = Translation.objects.filter(video=video).filter(
        target_language=target_language
    )

    if translation.filter(status="TRANSLATION_REVIEW_COMPLETE").first() is not None:
        translation_obj = translation.filter(
            status="TRANSLATION_REVIEW_COMPLETE"
        ).first()
        translation_payload = translation_obj.payload
        data = {}
        data["payload"] = []
        for segment in translation_payload["payload"]:
            if "target_text" in segment.keys() and len(segment["target_text"]) > 0:
                data["payload"].append(segment)
        return Response(
            {"id": translation_obj.id, "data": data},
            status=status.HTTP_200_OK,
        )
    elif translation.filter(status="TRANSLATION_EDIT_COMPLETE").first() is not None:
        translation_obj = translation.filter(status="TRANSLATION_EDIT_COMPLETE").first()
        translation_payload = translation_obj.payload
        data = {}
        data["payload"] = []
        for segment in translation_payload["payload"]:
            if "target_text" in segment.keys() and len(segment["target_text"]) > 0:
                data["payload"].append(segment)
        return Response(
            {"id": translation_obj.id, "data": data},
            status=status.HTTP_200_OK,
        )
    else:
        task = (
            Task.objects.filter(video=video)
            .filter(target_language=target_language)
            .filter(task_type="TRANSLATION_EDIT")
            .first()
        )
        translation_obj = get_translation_id(task)
        if translation_obj is not None:
            translation_payload = translation_obj.payload
            data = {}
            data["payload"] = []
            for segment in translation_payload["payload"]:
                if "target_text" in segment.keys() and len(segment["target_text"]) > 0:
                    data["payload"].append(segment)
            return Response(
                {"id": translation_obj.id, "data": data},
                status=status.HTTP_200_OK,
            )
        else:
            return Response(
                {"message": "No translation found"}, status=status.HTTP_404_NOT_FOUND
            )


@api_view(["GET"])
def retrieve_all_translations(request):
    """
    Endpoint to retrieve all translations for a video entry, regardless of status
    """
    if "video_id" not in dict(request.query_params):
        return Response(
            {"message": "missing param: video_id"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    video_id = request.query_params["video_id"]

    try:
        video = Video.objects.get(pk=video_id)
    except Video.DoesNotExist:
        return Response(
            {"message": "Video not found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    translations = Translation.objects.filter(video=video)
    if not translations.exists():
        return Response(
            {"message": "No translations found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    all_translations = []

    for translation_obj in translations:
        translation_payload = translation_obj.payload

        if isinstance(translation_payload, str):
            try:
                translation_payload = json.loads(translation_payload)
            except json.JSONDecodeError:
                translation_payload = {"payload": []}

        if not isinstance(translation_payload, dict):
            translation_payload = {"payload": []}

        data = {}
        data["payload"] = []

        for segment in translation_payload.get("payload", []):
            if "target_text" in segment and segment["target_text"]:
                data["payload"].append(segment)

        translation_data = {
            "id": translation_obj.id,
            "translation_uuid": translation_obj.translation_uuid,
            "translation_type": translation_obj.translation_type,
            "parent": translation_obj.parent_id,
            "transcript": translation_obj.transcript_id,
            "target_language": translation_obj.target_language,
            "user": translation_obj.user_id,
            "status": translation_obj.status,
            "data": data,
            "video": translation_obj.video_id,
            "task": translation_obj.task_id,
        }

        all_translations.append(translation_data)
    return Response(all_translations, status=status.HTTP_200_OK)


def get_translation_id(task):
    translation = Translation.objects.filter(task=task)
    if "EDIT" in task.task_type:
        if task.status == "NEW":
            translation_id = None
        elif task.status == "SELECTED_SOURCE":
            translation_id = (
                translation.filter(video=task.video)
                .filter(target_language=task.target_language)
                .filter(status="TRANSLATION_SELECT_SOURCE")
                .first()
            )
        elif task.status == "INPROGRESS":
            translation_id = (
                translation.filter(video=task.video)
                .filter(target_language=task.target_language)
                .filter(status="TRANSLATION_EDIT_INPROGRESS")
                .order_by("-updated_at")
                .first()
            )
        elif task.status == "REOPEN":
            translation_id = (
                translation.filter(video=task.video)
                .filter(target_language=task.target_language)
                .filter(status="TRANSLATION_EDIT_INPROGRESS")
                .order_by("-updated_at")
                .first()
            )
        elif task.status == "FAILED":
            translation_id = (
                translation.filter(video=task.video)
                .filter(target_language=task.target_language)
                .filter(status="TRANSLATION_EDIT_COMPLETE")
                .first()
            )
        elif task.status == "COMPLETE":
            translation_id = (
                translation.filter(video=task.video)
                .filter(target_language=task.target_language)
                .filter(status="TRANSLATION_EDIT_COMPLETE")
                .first()
            )
    else:
        if task.status == "NEW":
            translation_id = (
                translation.filter(video=task.video)
                .filter(target_language=task.target_language)
                .filter(status="TRANSLATION_REVIEWER_ASSIGNED")
                .first()
            )
        if task.status == "REOPEN":
            translation_id = (
                translation.filter(video=task.video)
                .filter(target_language=task.target_language)
                .filter(status="TRANSLATION_REVIEW_INPROGRESS")
                .first()
            )
        if task.status == "INPROGRESS":
            translation_id = (
                translation.filter(video=task.video)
                .filter(target_language=task.target_language)
                .filter(status="TRANSLATION_REVIEW_INPROGRESS")
                .first()
            )
        if task.status == "COMPLETE":
            translation_id = (
                translation.filter(video=task.video)
                .filter(target_language=task.target_language)
                .filter(status="TRANSLATION_REVIEW_COMPLETE")
                .first()
            )
    return translation_id
  
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
        404: "No translation found for given task",
    },
)
@api_view(["GET"])
def fetch_translation_status(request):
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

    translation = get_translation_id(task)
    if translation is not None:
        translation_id = translation.id
    try:
        translation = Translation.objects.get(pk=translation_id)
        return Response(
            {
                "message": "Status has been fetched successfully",
                "task_id": task.id,
                "translation_id": translation_id,
                "status": translation.status,
            },
            status=status.HTTP_200_OK,
        )
    except:
        return Response(
            {"message": "Translation doesn't exist."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    
@swagger_auto_schema(
    method="post",
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        required=["task_id", "trl_status"],
        properties={
            "task_id": openapi.Schema(
                type=openapi.TYPE_INTEGER,
                description="An integer identifying the translation instance",
            ),
            "trl_status": openapi.Schema(
                type=openapi.TYPE_STRING,
                description="Translation task status to be set",
            )
        },
        description="Post request body",
    ),
    responses={
        200: "Status has been updated successfully",
        400: "Bad request",
        404: "No translation found for given task",
    },
)
@api_view(["POST"])
def update_translation_status(request):
    if not request.user.is_authenticated:
        return Response({"message":"You do not have enough permissions to access this view!"}, status=401)
    try:
        # Get the required data from the POST body
        task_id = request.data["task_id"]
        trl_status = request.data["trl_status"]
    except KeyError:
        return Response(
            {
                "message": "Missing required parameters - task_id or trl_status"
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

    translation = get_translation_id(task)
    if translation is not None:
        translation_id = translation.id
    try:
        translation = Translation.objects.get(pk=translation_id)
        if trl_status in ["TRANSLATION_SELECT_SOURCE", "TRANSLATION_EDITOR_ASSIGNED", "TRANSLATION_EDIT_INPROGRESS", "TRANSLATION_EDIT_COMPLETE", "TRANSLATION_REVIEWER_ASSIGNED", "TRANSLATION_REVIEW_INPROGRESS", "TRANSLATION_REVIEW_COMPLETE"]:
            translation.status = trl_status
            translation.save()
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
            {"message": "Translation doesn't exist."},
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
    responses={200: "Returns the translation script."},
)
@api_view(["GET"])
def get_payload(request):
    try:
        task_id = request.query_params["task_id"]
        page = request.query_params["offset"]
        limit = request.query_params["limit"]
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

    translation = get_translation_id(task)
    if translation is not None:
        translation_id = translation.id
    else:
        return Response(
            {"message": "Translation doesn't exist."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Retrieve the transcript object
    try:
        translation = Translation.objects.get(pk=translation_id)
    except Translation.DoesNotExist:
        return Response(
            {"message": "Translation doesn't exist."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    start = (int(page) - 1) * int(limit)
    end = start + int(limit)
    page_records = translation.payload["payload"][start:end]
    records = translation.payload["payload"]

    total_pages = math.ceil(len(translation.payload["payload"]) / int(limit))
    next_page = int(page) + 1
    pre_page = int(page) - 1

    if next_page > total_pages:
        end = len(translation.payload["payload"])
        next_page = None

    if (pre_page <= 0) | (int(page) > total_pages):
        pre_page = None

    if len(page_records) == 0:
        return Response(
            {"payload": {"payload": []}, "source_type": translation.translation_type},
            status=status.HTTP_200_OK,
        )

    if "id" not in page_records[0].keys():
        for i in range(len(page_records)):
            page_records[i]["id"] = start + i

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
            "source_type": translation.translation_type,
            "count": len(translation.payload["payload"]),
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
    responses={200: "Returns the updated translation."},
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

    translation = get_translation_id(task)
    if translation is None:
        return Response(
            {"message": "Translation not found."},
            status=status.HTTP_404_NOT_FOUND,
        )
    else:
        translation_id = translation.id

    # Retrieve the translation object
    try:
        translation = Translation.objects.get(pk=translation_id)
    except Translation.DoesNotExist:
        return Response(
            {"message": "Translation doesn't exist."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Replace all occurrences of word_to_replace with replace_word
    for record in translation.payload["payload"]:
        if "target_text" in record:
            if replace_full_word:
                if transliteration_language == "en":
                    record["target_text"] = re.sub(
                        r"\b" + word_to_replace + r"\b",
                        replace_word,
                        record["target_text"],
                    )
                else:
                    record["target_text"] = record["target_text"].replace(
                        word_to_replace, replace_word
                    )
            else:
                record["target_text"] = record["target_text"].replace(
                    word_to_replace, replace_word
                )

    # Save the updated translation
    translation.save()

    return Response(
        {"message": "Translation updated successfully."},
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

    translation = get_translation_id(task)
    if translation is None:
        return Response(
            {"message": "Translation not found."},
            status=status.HTTP_404_NOT_FOUND,
        )
    else:
        translation_id = translation.id

    try:
        translation = Translation.objects.get(pk=translation_id)
    except Translation.DoesNotExist:
        return Response(
            {"message": "Translation not found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    save_index = -1
    for ind, sentence in enumerate(translation.payload["payload"]):
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
            ind < len(translation.payload["payload"]) - 1
            and type(translation.payload["payload"][ind + 1]) == dict
            and "text" in translation.payload["payload"][ind + 1].keys()
        ):
            end_time_of_next_sentence = datetime.datetime.strptime(
                translation.payload["payload"][ind + 1]["start_time"], "%H:%M:%S.%f"
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
    length_payload = len(translation.payload["payload"])
    sentence_offset = math.ceil((save_index + 1) / int(limit))
    response = get_payload_request(request, task_id, limit, sentence_offset)
    return Response(
        response.data,
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

    translation = get_translation_id(task)
    if translation is not None:
        translation_id = translation.id
    else:
        return Response(
            {"message": "Translation doesn't exist."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Retrieve the transcript object
    try:
        translation = Translation.objects.get(pk=translation_id)
    except Translation.DoesNotExist:
        return Response(
            {"message": "Translation doesn't exist."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    count = 0
    for sentence in translation.payload["payload"]:
        sentence["id"] = count
        count = count + 1

    return Response(
        {"payload": translation.payload, "source_type": translation.translation_type},
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


def send_mail_to_user(task):
    if task.user.enable_mail:
        if task.eta is not None:
            try:
                task_eta = str(task.eta.strftime("%Y-%m-%d"))
            except:
                task_eta = str(task.eta)
        else:
            task_eta = "-"
        logging.info("Send email to user %s", task.user.email)
        table_to_send = "<p><head><style>table, th, td {border: 1px solid black;border-collapse: collapse;}</style></head><body><table>"
        data = "<tr><th>Video Name</th><td>{name}</td></tr><tr><th>Video URL</th><td>{url}</td></tr><tr><th>Project Name</th><td>{project_name}</td></tr><tr><th>ETA</th><td>{eta}</td></tr><tr><th>Description</th><td>{description}</td></tr></table></body></p>".format(
            name=task.video.name,
            url=task.video.url,
            project_name=task.video.project_id.title,
            eta=task_eta,
            description=task.description,
        )
        final_table = table_to_send + data
        try:
            email = EmailMultiAlternatives(
                subject=f"{task.get_task_type_label} is active",
                body="Dear User, Following task is active.",
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[task.user.email],
            )
            email.attach_alternative(final_table, "text/html")
            email.send()
        except:
            logging.info("Error in sending Email")
    else:
        logging.info("Email is not enabled %s", task.user.email)


def check_if_translation_correct(translation_obj, task):
    bad_sentences = get_bad_sentences_in_progress(translation_obj, task)
    if len(bad_sentences) > 0:
        translation = (
            Translation.objects.filter(target_language=translation_obj.target_language)
            .filter(video=task.video)
            .filter(status="TRANSLATION_EDIT_INPROGRESS")
            .all()
        )
        if translation is not None:
            translation_obj.parent = None
            task.status = "INPROGRESS"
            translation.delete()
            translation_obj.status = "TRANSLATION_EDIT_INPROGRESS"
        else:
            translation = (
                Translation.objects.filter(
                    target_language=translation_obj.target_language
                )
                .filter(video=task.video)
                .filter(status="TRANSLATION_SELECT_SOURCE")
                .first()
            )
            translation_obj.parent = None
            translation.delete()
            task.status = "SELECTED_SOURCE"
            translation_obj.status = "TRANSLATION_SELECT_SOURCE"
        task.save()
        translation_obj.save()
        response = {
            "data": bad_sentences,
            "message": "Translation task couldn't be completed. Please correct the following sentences.",
        }
        return response
    return None


def change_active_status_of_next_tasks(task, translation_obj):
    translation_review_task = (
        Task.objects.filter(video=task.video)
        .filter(target_language=translation_obj.target_language)
        .filter(task_type="TRANSLATION_REVIEW")
        .first()
    )
    if translation_review_task:
        translation = (
            Translation.objects.filter(target_language=translation_obj.target_language)
            .filter(video=task.video)
            .filter(status="TRANSLATION_REVIEWER_ASSIGNED")
            .first()
        )
        if translation is not None:
            translation_review_task.is_active = True
            translation.transcript = translation_obj.transcript
            translation.payload = translation_obj.payload
            translation.save()
            translation_review_task.save()
            try:
                send_mail_to_user(translation_review_task)
            except:
                logging.info("Error in sending mail to VoiceOver Editor")
    voice_over_task = (
        Task.objects.filter(task_type="VOICEOVER_EDIT")
        .filter(video=task.video)
        .filter(target_language=task.target_language)
        .first()
    )
    if (
        voice_over_task is not None
        and task.task_type == "TRANSLATION_EDIT"
        and translation_review_task is None
    ):
        activate_voice_over = True
    elif (
        voice_over_task is not None
        and task.task_type == "TRANSLATION_REVIEW"
        and "COMPLETE" in translation_obj.status
    ):
        activate_voice_over = True
    else:
        activate_voice_over = False
    if activate_voice_over:
        voice_over_obj = (
            VoiceOver.objects.filter(video=task.video)
            .filter(target_language=task.target_language)
            .first()
        )
        source_type = (
            task.video.project_id.default_voiceover_type
            or task.video.project_id.organization_id.default_voiceover_type
        )
        if source_type is None:
            source_type = config.backend_default_voice_over_type
        if voice_over_task is not None:
            tts_payload = process_translation_payload(
                translation_obj, voice_over_task.target_language
            )
            if type(tts_payload) == dict and "message" in tts_payload.keys():
                message = tts_payload["message"]
                logging.info("Error from TTS API")
                voice_over_task.status = "FAILED"
                voice_over_task.save()
                set_fail_for_translation_task(task)
                return message
            if source_type == "MANUALLY_CREATED":
                voice_over_obj.translation = translation_obj
                voice_over_obj.save()
                voice_over_task.is_active = True
                voice_over_task.save()
                try:
                    send_mail_to_user(voice_over_task)
                except:
                    logging.info("Error in sending mail to VO Editor.")
            else:
                (
                    tts_input,
                    target_language,
                    translation,
                    translation_id,
                    empty_sentences,
                ) = tts_payload
                logging.info("Async call for TTS")
                celery_tts_call.delay(
                    voice_over_task.id,
                    tts_input,
                    target_language,
                    translation,
                    translation_id,
                    empty_sentences,
                )
    else:
        logging.info("No change in status")
    return None


@swagger_auto_schema(
    method="post",
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        required=["task_id"],
        properties={
            "task_id": openapi.Schema(
                type=openapi.TYPE_INTEGER,
                description="An integer identifying the task instance",
            ),
        },
        description="Generate Translation payload",
    ),
    responses={
        200: "Translation has been generated",
    },
)
@api_view(["POST"])
def generate_translation_output(request):
    task_id = request.data.get("task_id")
    if task_id is None:
        return Response(
            {"message": "Missing required parameters - task_id"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    user = request.user

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

    translation = (
        Translation.objects.filter(video=task.video)
        .filter(status="TRANSLATION_SELECT_SOURCE")
        .filter(target_language=task.target_language)
        .first()
    )
    if translation is not None:
        if (
            translation.payload is not None
            and type(translation.payload) == dict
            and "payload" in translation.payload.keys()
        ):
            return Response(
                {"message": "Payload for translation is generated."},
                status=status.HTTP_200_OK,
            )
        project = Project.objects.get(id=task.video.project_id.id)
        organization = project.organization_id
        source_type = (
            project.default_translation_type or organization.default_translation_type
        )
        if source_type == None:
            source_type = config.backend_default_translation_type
        payloads = generate_translation_payload(
            translation.transcript,
            translation.target_language,
            [source_type],
            task.user.id,
        )
        if type(translation.payload) == str or (
            type(translation.payload) == dict
            and "payload" not in translation.payload.keys()
        ):
            if (
                type(translation.payload) == dict
                and "speaker_info" in translation.payload
            ):
                translation.payload["payload"] = payloads[source_type]["payload"]
            else:
                translation.payload = payloads[source_type]
            translation.save()
        return Response(
            {"message": "Payload for translation is generated."},
            status=status.HTTP_200_OK,
        )
    else:
        return Response(
            {"message": "Please wait while the translation is generated."},
            status=status.HTTP_200_OK,
        )


def modify_payload(limit, payload, start_offset, end_offset, translation):
    count_sentences = len(translation.payload["payload"])
    for i in range(len(payload["payload"])):
        if "retranslate" in payload["payload"][i].keys():
            translated_text = get_batch_translations_using_indictrans_nmt_api(
                [payload["payload"][i]["text"]],
                translation.video.language,
                translation.task.target_language,
            )
            if type(translated_text) == list:
                payload["payload"][i]["target_text"] = translated_text[0]
            else:
                logging.info(
                    "Failed to retranslate for task_id %s", str(translation.task.id)
                )
    if len(payload["payload"]) == limit:
        length = len(payload["payload"])
        length_2 = -1
        if end_offset > count_sentences:
            length_2 = end_offset - count_sentences
            length = length - length_2
        for i in range(length):
            if (
                "text" in payload["payload"][i].keys()
                and "text" in translation.payload["payload"][start_offset + i]
            ):
                translation.payload["payload"][start_offset + i] = {
                    "start_time": payload["payload"][i]["start_time"],
                    "end_time": payload["payload"][i]["end_time"],
                    "text": payload["payload"][i]["text"],
                    "target_text": payload["payload"][i]["target_text"],
                    "speaker_id": payload["payload"][i].get("speaker_id", ""),
                }
            elif (
                "text" in payload["payload"][i].keys()
                and "text" not in translation.payload["payload"][start_offset + i]
            ):
                translation.payload["payload"][start_offset + i] = {
                    "start_time": payload["payload"][i]["start_time"],
                    "end_time": payload["payload"][i]["end_time"],
                    "text": payload["payload"][i]["text"],
                    "target_text": payload["payload"][i]["target_text"],
                    "speaker_id": payload["payload"][i].get("speaker_id", ""),
                }
            else:
                translation.payload["payload"][start_offset + i] = {}
        if length_2 > 0:
            for i in range(length_2):
                if "text" in payload["payload"][i].keys():
                    translation.payload["payload"].insert(
                        start_offset + i + length,
                        {
                            "start_time": payload["payload"][length + i]["start_time"],
                            "end_time": payload["payload"][length + i]["end_time"],
                            "text": payload["payload"][length + i]["text"],
                            "target_text": payload["payload"][length + i][
                                "target_text"
                            ],
                            "speaker_id": payload["payload"][length + i].get(
                                "speaker_id", ""
                            ),
                        },
                    )
                else:
                    logging.info("Text missing in payload")
    elif len(payload["payload"]) < limit:
        logging.info("Limit is less than length of payload")
        length = len(payload["payload"])
        length_2 = -1
        length_3 = -1
        if end_offset > count_sentences:
            if length > len(translation.payload["payload"][start_offset:end_offset]):
                length_2 = length - len(
                    translation.payload["payload"][start_offset:end_offset]
                )
                length = length - length_2
            else:
                length_3 = (
                    len(translation.payload["payload"][start_offset:end_offset])
                    - length
                )
            for i in range(length):
                if (
                    "text" in payload["payload"][i].keys()
                    and "text" in translation.payload["payload"][start_offset + i]
                ):
                    translation.payload["payload"][start_offset + i] = {
                        "start_time": payload["payload"][i]["start_time"],
                        "end_time": payload["payload"][i]["end_time"],
                        "text": payload["payload"][i]["text"],
                        "target_text": payload["payload"][i]["target_text"],
                        "speaker_id": payload["payload"][i].get("speaker_id", ""),
                    }
                elif (
                    "text" in payload["payload"][i].keys()
                    and "text" not in translation.payload["payload"][start_offset + i]
                ):
                    translation.payload["payload"][start_offset + i] = {
                        "start_time": payload["payload"][i]["start_time"],
                        "end_time": payload["payload"][i]["end_time"],
                        "text": payload["payload"][i]["text"],
                        "speaker_id": payload["payload"][i].get("speaker_id"),
                        "target_text": payload["payload"][i]["target_text"],
                    }
                else:
                    logging.info("Text missing in payload")
            if length_2 > 0:
                for i in range(length_2):
                    if "text" in payload["payload"][i].keys():
                        translation.payload["payload"].insert(
                            start_offset + i + length,
                            {
                                "start_time": payload["payload"][length + i][
                                    "start_time"
                                ],
                                "end_time": payload["payload"][length + i]["end_time"],
                                "text": payload["payload"][length + i]["text"],
                                "target_text": payload["payload"][length + i][
                                    "target_text"
                                ],
                                "speaker_id": payload["payload"][length + i].get(
                                    "speaker_id", ""
                                ),
                            },
                        )
                    else:
                        logging.info("Text missing in payload")
            if length_3 > 0:
                for i in range(length_3):
                    translation.payload["payload"][start_offset + i + length] = {}
        else:
            for i in range(length):
                if (
                    "text" in payload["payload"][i].keys()
                    and "text" in translation.payload["payload"][start_offset + i]
                ):
                    translation.payload["payload"][start_offset + i] = {
                        "start_time": payload["payload"][i]["start_time"],
                        "end_time": payload["payload"][i]["end_time"],
                        "text": payload["payload"][i]["text"],
                        "target_text": payload["payload"][i]["target_text"],
                        "speaker_id": payload["payload"][i].get("speaker_id", ""),
                    }
                elif (
                    "text" in payload["payload"][i].keys()
                    and "text" not in translation.payload["payload"][start_offset + i]
                ):
                    translation.payload["payload"][start_offset + i] = {
                        "start_time": payload["payload"][i]["start_time"],
                        "end_time": payload["payload"][i]["end_time"],
                        "text": payload["payload"][i]["text"],
                        "speaker_id": payload["payload"][i].get("speaker_id"),
                        "target_text": payload["payload"][i]["target_text"],
                    }
                else:
                    logging.info("Text missing in payload")
            delete_indices = []
            for i in range(limit - length):
                delete_indices.append(start_offset + i + length)

            logging.info("delete_indices %s", str(delete_indices))
            for ind in delete_indices:
                translation.payload["payload"][ind] = {}
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
            if (
                "text" in payload["payload"][i].keys()
                and "text" in translation.payload["payload"][start_offset + i]
            ):
                translation.payload["payload"][start_offset + i] = {
                    "start_time": payload["payload"][i]["start_time"],
                    "end_time": payload["payload"][i]["end_time"],
                    "text": payload["payload"][i]["text"],
                    "target_text": payload["payload"][i]["target_text"],
                    "speaker_id": payload["payload"][i].get("speaker_id", ""),
                }
            elif "text" not in translation.payload["payload"][start_offset + i]:
                translation.payload["payload"][start_offset + i] = {
                    "start_time": payload["payload"][i]["start_time"],
                    "end_time": payload["payload"][i]["end_time"],
                    "text": payload["payload"][i]["text"],
                    "speaker_id": payload["payload"][i].get("speaker_id", ""),
                    "target_text": payload["payload"][i]["target_text"],
                }
            else:
                logging.info("Text missing in payload")
        for i in range(length_2):
            if "text" in payload["payload"][i].keys():
                if (
                    len(translation.payload["payload"]) > insert_at + i
                    and "text" in translation.payload["payload"][insert_at + i].keys()
                    and payload["payload"][length + i]["start_time"]
                    == translation.payload["payload"][insert_at + i]["start_time"]
                    and payload["payload"][length + i]["end_time"]
                    == translation.payload["payload"][insert_at + i]["end_time"]
                ):
                    translation.payload["payload"][insert_at + i] = {
                        "start_time": payload["payload"][length + i]["start_time"],
                        "end_time": payload["payload"][length + i]["end_time"],
                        "text": payload["payload"][length + i]["text"],
                        "target_text": payload["payload"][length + i]["target_text"],
                        "speaker_id": payload["payload"][length + i].get(
                            "speaker_id", ""
                        ),
                    }
                else:
                    translation.payload["payload"].insert(
                        insert_at + i,
                        {
                            "start_time": payload["payload"][length + i]["start_time"],
                            "end_time": payload["payload"][length + i]["end_time"],
                            "text": payload["payload"][length + i]["text"],
                            "target_text": payload["payload"][length + i][
                                "target_text"
                            ],
                            "speaker_id": payload["payload"][length + i].get(
                                "speaker_id", ""
                            ),
                        },
                    )
            else:
                logging.info("Text missing in payload")


@swagger_auto_schema(
    method="post",
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        required=["task_id", "payload"],
        properties={
            "task_id": openapi.Schema(
                type=openapi.TYPE_INTEGER,
                description="An integer identifying the translation instance",
            ),
            "payload": openapi.Schema(
                type=openapi.TYPE_OBJECT,
                description="A string to pass the translated subtitles and metadata",
            ),
        },
        description="Post request body",
    ),
    responses={
        200: "Translation has been created/updated successfully",
        400: "Bad request",
        404: "No translation found for the given transcript_id and target_language",
    },
)
@api_view(["POST"])
def save_translation(request):
    try:
        # Get the required data from the POST body
        translation_id = request.data.get("translation_id", None)
        payload = request.data["payload"]
        task_id = request.data["task_id"]
        offset = request.data["offset"]
        limit = request.data["limit"]
    except KeyError:
        return Response(
            {
                "message": "Missing required parameters - language or payload or task_id or translation_id"
            },
            status=status.HTTP_400_BAD_REQUEST,
        )
    user = request.user

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

    translation = get_translation_id(task)
    start_offset = (int(offset) - 1) * int(limit)
    end_offset = start_offset + int(limit)
    if translation is not None:
        translation_id = translation.id
    else:
        return Response(
            {"message": "Translation doesn't exist."},
            status=status.HTTP_400_BAD_REQUEST,
        )
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
    try:
        translation = Translation.objects.get(pk=translation_id)
        target_language = translation.target_language
        video = translation.video
        message = None
        if (
            type(payload) != dict
            or "payload" not in payload.keys()
            or len(payload["payload"]) == 0
            or "text" not in payload["payload"][0].keys()
        ):
            return Response(
                {"message": "Invalid Translation."}, status=status.HTTP_400_BAD_REQUEST
            )
        # Check if the transcript has a user
        if task.user != request.user:
            return Response(
                {"message": "You are not allowed to update this translation."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        else:
            if translation.status == TRANSLATION_REVIEW_COMPLETE:
                return Response(
                    {
                        "message": "Translation can't be edited, as the final translation already exists"
                    },
                    status=status.HTTP_201_CREATED,
                )

            if "EDIT" in task.task_type:
                if request.data.get("final"):
                    if (
                        Translation.objects.filter(status=TRANSLATION_EDIT_COMPLETE)
                        .filter(target_language=target_language)
                        .filter(video=translation.video)
                        .first()
                        is not None
                    ):
                        if task.status == "INPROGRESS":
                            task.status = "COMPLETE"
                            task.completed = {
                            "completed_by": request.user.id,
                            "timestamp": now().isoformat(),
                            }
                            task.save()
                        return Response(
                            {"message": "Edit Translation already exists."},
                            status=status.HTTP_201_CREATED,
                        )
                    else:
                        ts_status = TRANSLATION_EDIT_COMPLETE
                        translation_type = translation.translation_type
                        translation_obj = Translation.objects.create(
                            translation_type=translation_type,
                            parent=translation,
                            transcript=translation.transcript,
                            video=translation.video,
                            target_language=translation.target_language,
                            user=user,
                            payload=translation.payload,
                            status=ts_status,
                            task=task,
                        )
                        modify_payload(
                            limit, payload, start_offset, end_offset, translation_obj
                        )
                        translation_obj.save()
                        task.status = "COMPLETE"
                        task.save()
                        translation_obj.save()
                        response = check_if_translation_correct(translation_obj, task)
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
                            translation_obj.payload["payload"]
                        ):
                            if "text" not in sentence.keys():
                                delete_indices.append(index)

                        delete_indices.reverse()
                        for ind in delete_indices:
                            translation_obj.payload["payload"].pop(ind)
                        translation_obj.save()
                        message = change_active_status_of_next_tasks(
                            task, translation_obj
                        )
                else:
                    translation_obj = (
                        Translation.objects.filter(status=TRANSLATION_EDIT_INPROGRESS)
                        .filter(target_language=target_language)
                        .filter(video=translation.video)
                        .first()
                    )
                    ts_status = TRANSLATION_EDIT_INPROGRESS
                    if translation_obj is not None:
                        translation_obj = (
                            Translation.objects.filter(
                                status=TRANSLATION_EDIT_INPROGRESS
                            )
                            .filter(target_language=target_language)
                            .filter(video=translation.video)
                            .order_by("-updated_at")
                            .first()
                        )
                        modify_payload(
                            limit,
                            payload,
                            start_offset,
                            end_offset,
                            translation_obj,
                        )
                        translation_obj.save()
                        # logging.info("Error in saving translation")
                    else:
                        translation_obj = (
                            Translation.objects.filter(status=TRANSLATION_SELECT_SOURCE)
                            .filter(target_language=target_language)
                            .filter(video=translation.video)
                            .first()
                        )
                        if translation_obj is None:
                            return Response(
                                {"message": "Translation object does not exist."},
                                status=status.HTTP_404_NOT_FOUND,
                            )
                        translation_obj = Translation.objects.create(
                            translation_type=translation_obj.translation_type,
                            parent=translation_obj,
                            transcript=translation_obj.transcript,
                            video=translation_obj.video,
                            target_language=translation_obj.target_language,
                            user=user,
                            payload=translation_obj.payload,
                            status=ts_status,
                            task=task,
                        )
                        modify_payload(
                            limit, payload, start_offset, end_offset, translation_obj
                        )
                        translation_obj.save()
                        task.status = "INPROGRESS"
                        task.save()
            else:
                if request.data.get("final"):
                    if (
                        Translation.objects.filter(status=TRANSLATION_REVIEW_COMPLETE)
                        .filter(target_language=target_language)
                        .filter(video=video)
                        .first()
                        is not None
                    ):
                        return Response(
                            {"message": "Reviewed Translation already exists."},
                            status=status.HTTP_201_CREATED,
                        )
                    ts_status = TRANSLATION_REVIEW_COMPLETE
                    translation_obj = Translation.objects.create(
                        translation_type=translation.translation_type,
                        parent=translation,
                        transcript=translation.transcript,
                        video=translation.video,
                        target_language=translation.target_language,
                        user=user,
                        payload=translation.payload,
                        status=ts_status,
                        task=task,
                    )
                    modify_payload(
                        limit, payload, start_offset, end_offset, translation_obj
                    )
                    translation_obj.save()
                    translation_obj.save()
                    task.status = "COMPLETE"
                    task.save()
                    response = check_if_translation_correct(translation_obj, task)
                    if type(response) == dict:
                        return Response(
                            {"data": response["data"], "message": response["message"]},
                            status=status.HTTP_400_BAD_REQUEST,
                        )
                    delete_indices = []
                    for index, sentence in enumerate(
                        translation_obj.payload["payload"]
                    ):
                        if "text" not in sentence.keys():
                            delete_indices.append(index)

                    delete_indices.reverse()
                    for ind in delete_indices:
                        translation_obj.payload["payload"].pop(ind)
                    message = change_active_status_of_next_tasks(task, translation_obj)
                else:
                    translation_obj = (
                        Translation.objects.filter(status=TRANSLATION_REVIEW_INPROGRESS)
                        .filter(target_language=target_language)
                        .filter(video=video)
                        .first()
                    )
                    ts_status = TRANSLATION_REVIEW_INPROGRESS
                    translation_type = translation.translation_type
                    if translation_obj is not None:
                        modify_payload(
                            limit, payload, start_offset, end_offset, translation_obj
                        )
                        translation_obj.translation_type = translation_type
                        translation_obj.save()
                        task.status = "INPROGRESS"
                        task.save()
                    else:
                        ts_status = TRANSLATION_REVIEW_INPROGRESS
                        translation_obj = Translation.objects.create(
                            translation_type=translation.translation_type,
                            parent=translation,
                            transcript=translation.transcript,
                            video=translation.video,
                            target_language=translation.target_language,
                            user=user,
                            payload=translation.payload,
                            status=ts_status,
                            task=task,
                        )
                        modify_payload(
                            limit, payload, start_offset, end_offset, translation_obj
                        )
                        translation_obj.save()
                        task.status = "INPROGRESS"
                        task.save()
            if request.data.get("final"):
                if message is not None:
                    full_message = "Translation updated successfully. " + message
                else:
                    full_message = "Translation updated successfully."

                delete_indices = []
                for index, sentence in enumerate(translation_obj.payload["payload"]):
                    if "text" not in sentence.keys():
                        delete_indices.append(index)

                delete_indices.reverse()
                for ind in delete_indices:
                    translation_obj.payload["payload"].pop(ind)

                if (
                    translation_obj.payload != ""
                    and translation_obj.payload is not None
                ):
                    num_words = 0
                    for idv_translation in translation_obj.payload["payload"]:
                        if "target_text" in idv_translation.keys():
                            cleaned_text = regex.sub(
                                r"[^\p{L}\s]", "", idv_translation["target_text"]
                            ).lower()  # for removing special characters
                            cleaned_text = regex.sub(
                                r"\s+", " ", cleaned_text
                            )  # for removing multiple blank spaces
                            num_words += len(cleaned_text.split(" "))
                            translation_obj.payload["payload"][index][
                                "start_time"
                            ] = format_timestamp(
                                translation_obj.payload["payload"][index]["start_time"]
                            )
                            translation_obj.payload["payload"][index][
                                "end_time"
                            ] = format_timestamp(
                                translation_obj.payload["payload"][index]["end_time"]
                            )

                    translation_obj.payload["word_count"] = num_words
                    translation_obj.save()
                return Response(
                    {
                        "message": full_message,
                        "task_id": task.id,
                        "translation_id": translation_obj.id,
                        # "data": translation_obj.payload,
                    },
                    status=status.HTTP_200_OK,
                )
            else:
                return Response(
                    {
                        "task_id": task.id,
                        "translation_id": translation_obj.id,
                        # "data": translation_obj.payload,
                        "message": "Saved as draft.",
                    },
                    status=status.HTTP_200_OK,
                )
    except Translation.DoesNotExist:
        return Response(
            {"message": "Translation doesn't exist."},
            status=status.HTTP_400_BAD_REQUEST,
        )


@api_view(["GET"])
@authentication_classes([])
@permission_classes([])
def get_translation_supported_languages(request):
    """
    Endpoint to get the supported languages for TTS API
    """
    return Response(
        [
            {"label": label, "value": value}
            for label, value in TRANSLATION_SUPPORTED_LANGUAGES.items()
        ],
        status=status.HTTP_200_OK,
    )


@swagger_auto_schema(
    method="get",
    manual_parameters=[
        openapi.Parameter(
            "task_id",
            openapi.IN_QUERY,
            description=("A string to pass the transcript uuid"),
            type=openapi.TYPE_STRING,
            required=True,
        ),
    ],
    responses={200: "Get Speaker info in target language."},
)
@api_view(["GET"])
def get_speaker_info(request):
    if "task_id" not in dict(request.query_params):
        return Response(
            {"message": "missing param : task_id"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    task_id = request.query_params["task_id"]

    try:
        task = Task.objects.get(pk=task_id)
    except Task.DoesNotExist:
        return Response(
            {"message": "Task not found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    if task.video.multiple_speaker == True:
        speakers_info = task.video.speaker_info
        target_language = task.target_language
        speaker_output = []
        for speaker_info in speakers_info:
            name = speaker_info["id"]
            json_data = {
                "input": [{"source": name}],
                "config": {
                    "language": {
                        "sourceLanguage": task.video.language,
                        "targetLanguage": task.target_language,
                    },
                    "isSentence": True,
                },
            }
            logging.info("Calling Transliteration API")
            response = requests.post(
                config.transliteration_url,
                headers={"authorization": config.dhruva_key},
                json=json_data,
            )
            transliteration_output = response.json()
            speaker_output.append(
                {
                    "label": name,
                    "value": transliteration_output["output"][0]["target"][0],
                }
            )
        translation_obj = (
            Translation.objects.filter(task=task)
            .filter(status=TRANSLATION_SELECT_SOURCE)
            .first()
        )
        translation_obj.payload = {}
        translation_obj.payload["speaker_info"] = speaker_output
        translation_obj.save()
        return Response(
            {"speaker_info": speaker_output},
            status=status.HTTP_200_OK,
        )
    else:
        return Response(
            {
                "message": "Can not retrieve multiple speakers info as there is only one speaker in this video."
            },
            status=status.HTTP_404_NOT_FOUND,
        )


@swagger_auto_schema(
    method="post",
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        required=["task_id"],
        properties={
            "task_id": openapi.Schema(
                type=openapi.TYPE_INTEGER,
                description="An integer identifying the task instance",
            ),
            "speaker_info": openapi.Schema(
                type=openapi.TYPE_OBJECT,
                description="An object consisting details of speaker",
            ),
        },
        description="Update Speaker Info.",
    ),
    responses={
        200: "Speaker info has been updated.",
    },
)
@api_view(["POST"])
def update_speaker_info(request):
    task_id = request.data.get("task_id")
    speaker_info = request.data.get("speaker_info")
    if task_id is None:
        return Response(
            {"message": "Missing required parameters - task_id"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        task = Task.objects.get(pk=task_id)
    except Task.DoesNotExist:
        return Response(
            {"message": "Task not found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    translation_obj = (
        Translation.objects.filter(task=task)
        .filter(status="TRANSLATION_SELECT_SOURCE")
        .first()
    )
    translation_obj.payload = {}
    translation_obj.payload["speaker_info"] = speaker_info
    translation_obj.save()
    return Response(
        {"message": "Updated speaker info"},
        status=status.HTTP_200_OK,
    )


@swagger_auto_schema(
    method="get",
    manual_parameters=[
        openapi.Parameter(
            "transcript_id",
            openapi.IN_QUERY,
            description=("A string to pass the transcript uuid"),
            type=openapi.TYPE_STRING,
            required=True,
        ),
        openapi.Parameter(
            "target_language",
            openapi.IN_QUERY,
            description=("A string to pass the target language of the translation"),
            type=openapi.TYPE_STRING,
            required=True,
        ),
        openapi.Parameter(
            "batch_size",
            openapi.IN_QUERY,
            description=("An integer to pass the batch size"),
            type=openapi.TYPE_STRING,
            required=False,
        ),
    ],
    responses={
        200: "Generates the translation for the given transcript_id and target_language"
    },
)
@api_view(["GET"])
@is_translation_editor
def generate_translation(request):
    """GET Request endpoint to generate translation for a given transcript_id and target_language

    Args:
        request : HTTP GET request

    GET params:
        transcript_id : UUID of the transcript
        target_language : Target language of the translation
        batch_size : Number of transcripts to be translated at a time [optional]

    Returns:
        Response: Response containing the generated translations
    """

    # Get the query params
    transcript_id = request.query_params.get("transcript_id")
    target_language = request.query_params.get("target_language")
    batch_size = request.query_params.get("batch_size", 75)

    # Ensure that required params are present
    if not (transcript_id and target_language):
        return Response(
            {
                "message": "Missing required query params [transcript_id, target_language]."
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Check if the given transcript ID exists
    transcript = get_object_or_404(Transcript, pk=transcript_id)

    # Get the transcript source language
    source_lang = transcript.language

    # Check if the cached translation is valid and return if it is valid

    translation = (
        Translation.objects.filter(
            transcript=transcript_id,
            target_language=target_language,
            translation_type=MACHINE_GENERATED,
        )
        .order_by("-updated_at")
        .first()
    )
    if translation is not None:
        if (
            translation.updated_at - translation.transcript.updated_at
        ).total_seconds() >= 0:
            serializer = TranslationSerializer(translation)
            return Response(serializer.data, status=status.HTTP_200_OK)

    # If there is no cached translation, create a new one
    translation = Translation.objects.create(
        translation_type=MACHINE_GENERATED,
        transcript_id=transcript_id,
        target_language=target_language,
        user=None,
        payload={},
    )

    # Read the sentences from the transcript
    sentence_list = []
    vtt_output = transcript.payload["output"]
    for vtt_line in webvtt.read_buffer(StringIO(vtt_output)):
        sentence_list.append(vtt_line.text)

    all_translated_sentences = []  # List to store all the translated sentences

    # Iterate over the sentences in batch format and send them to the Translation API
    for i in range(0, len(sentence_list), batch_size):
        batch_of_input_sentences = sentence_list[i : i + batch_size]

        # Get the translation using the Indictrans NMT API
        translations_output = get_batch_translations_using_indictrans_nmt_api(
            sentence_list=batch_of_input_sentences,
            source_language=source_lang,
            target_language=target_language,
        )

        # Check if translations output doesn't return a string error
        if isinstance(translations_output, str):
            return Response(
                {"message": translations_output}, status=status.HTTP_400_BAD_REQUEST
            )
        else:
            # Add the translated sentences to the list
            all_translated_sentences.extend(translations_output)

    # Check if the length of the translated sentences is equal to the length of the input sentences
    if len(all_translated_sentences) != len(sentence_list):
        return Response(
            {"message": "Error while generating translation."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Update the translation payload with the generated translations
    payload = []
    for source, target in zip(sentence_list, all_translated_sentences):
        payload.append(
            {"source": source, "target": target if source.strip() else source}
        )
    translation.payload = {"translations": payload}
    translation.save()

    # Return the translation
    serializer = TranslationSerializer(translation)
    return Response(serializer.data, status=status.HTTP_200_OK)


@api_view(["GET"])
def get_translation_types(request):
    """
    Fetches all translation types.
    """
    data = [
        {"label": translation_type[1], "value": translation_type[0]}
        for translation_type in TRANSLATION_TYPE_CHOICES
    ]
    return Response(data, status=status.HTTP_200_OK)


@api_view(["GET"])
@authentication_classes([])
@permission_classes([])
def get_translation_report(request):
    start_date_str = request.query_params.get("start_date")
    end_date_str = request.query_params.get("end_date")

    translations = Translation.objects.filter(status="TRANSLATION_EDIT_COMPLETE")

    def parse_date(date_str):
        year, month, day = map(int, date_str.split("-"))
        return timezone.make_aware(datetime.datetime(year, month, day, 0, 0, 0))

    if start_date_str and end_date_str:
        start_date = parse_date(start_date_str)
        end_date = parse_date(end_date_str) + timedelta(days=1)
        translations = translations.filter(
            updated_at__date__range=(start_date.date(), end_date.date())
        )

    translations = translations.exclude(
        video__project_id__organization_id__title__isnull=True
    ).values(
        "video__project_id__organization_id__title",
        "video__project_id__organization_id__is_active",
        src_language=F("video__language"),
        tgt_language=F("target_language"),
    )

    translation_statistics = (
        translations.annotate(transcripts_translated=Count("id"))
        .annotate(translation_duration=Sum(F("video__duration")))
        .order_by("-translation_duration")
    )
    translation_data = []
    for elem in translation_statistics:
        org_name = elem.get("video__project_id__organization_id__title")
        is_active = elem.get("video__project_id__organization_id__is_active", False)
        if not org_name:
            continue

        translation_dict = {
            "org": {
                "name": org_name,
                "is_active": is_active,
            },
            "src_language": {
                "value": dict(TRANSLATION_LANGUAGE_CHOICES)[elem["src_language"]],
                "label": "Source Langauge",
                "viewColumns": False,
            },
            "tgt_language": {
                "value": dict(TRANSLATION_LANGUAGE_CHOICES)[elem["tgt_language"]],
                "label": "Target Language",
                "viewColumns": False,
            },
            "translation_duration": {
                "value": round(elem["translation_duration"].total_seconds() / 3600, 3),
                "label": "Translated Duration (Hours)",
            },
            "transcripts_translated": {
                "value": elem["transcripts_translated"],
                "label": "Translation Tasks Count",
            },
        }
        translation_data.append(translation_dict)

    translation_data.sort(key=lambda x: x["org"]["name"])

    res = []
    for org, items in groupby(translation_data, key=lambda x: x["org"]["name"]):
        lang_data = []
        is_active_status = None
        for i in items:
            is_active_status = i["org"]["is_active"]  
            del i["org"]
            lang_data.append(i)
        temp_data = {"org": {"name": org, "is_active": is_active_status}, "data": lang_data}
        res.append(temp_data)
        
    return Response(res, status=status.HTTP_200_OK)

def regenerate_translation_voiceover(task_id):
    task_obj = Task.objects.get(pk=task_id)
    transcription_task = Task.objects.filter(video=task_obj.video, task_type="TRANSCRIPTION_EDIT", status="COMPLETE").first()
    if transcription_task is None:
        return False
    transcript = get_transcript_id(transcription_task)
    transcript_obj = Transcript.objects.get(pk=transcript.id)
    translation = Translation.objects.filter(task=task_obj).first()
    translation.transcript = transcript_obj
    translation.save()
    celery_nmt_tts_call.delay(task_id)
    return True
