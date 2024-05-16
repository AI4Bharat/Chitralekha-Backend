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
from .models import TranslationVoiceover 
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



def get_translation_id(task):
    translationvoiceover = TranslationVoiceover.objects.filter(task=task)
    if "EDIT" in task.task_type:
        if task.status == "NEW":
            translation_id = None
        elif task.status == "SELECTED_SOURCE":
            translation_id = (
                translationvoiceover.filter(video=task.video)
                .filter(target_language=task.target_language)
                .filter(translation_status="TRANSLATION_SELECT_SOURCE")
                .first()
            )
        elif task.status == "INPROGRESS":
            translation_id = (
                translationvoiceover.filter(video=task.video)
                .filter(target_language=task.target_language)
                .filter(translation_status="TRANSLATION_EDIT_INPROGRESS")
                .order_by("-updated_at")
                .first()
            )
        elif task.status == "REOPEN":
            translation_id = (
                translationvoiceover.filter(video=task.video)
                .filter(target_language=task.target_language)
                .filter(translation_status="TRANSLATION_EDIT_INPROGRESS")
                .order_by("-updated_at")
                .first()
            )
        elif task.status == "FAILED":
            translation_id = (
                translationvoiceover.filter(video=task.video)
                .filter(target_language=task.target_language)
                .filter(translation_status="TRANSLATION_EDIT_COMPLETE")
                .first()
            )
        elif task.status == "COMPLETE":
            translation_id = (
                translationvoiceover.filter(video=task.video)
                .filter(target_language=task.target_language)
                .filter(translation_status="TRANSLATION_EDIT_COMPLETE")
                .first()
            )
    else:
        if task.status == "NEW":
            translation_id = (
                translationvoiceover.filter(video=task.video)
                .filter(target_language=task.target_language)
                .filter(translation_status="TRANSLATION_REVIEWER_ASSIGNED")
                .first()
            )
        if task.status == "REOPEN":
            translation_id = (
                translationvoiceover.filter(video=task.video)
                .filter(target_language=task.target_language)
                .filter(translation_status="TRANSLATION_REVIEW_INPROGRESS")
                .first()
            )
        if task.status == "INPROGRESS":
            translation_id = (
                translationvoiceover.filter(video=task.video)
                .filter(target_language=task.target_language)
                .filter(translation_status="TRANSLATION_REVIEW_INPROGRESS")
                .first()
            )
        if task.status == "COMPLETE":
            translation_id = (
                translationvoiceover.filter(video=task.video)
                .filter(target_language=task.target_language)
                .filter(translation_status="TRANSLATION_REVIEW_COMPLETE")
                .first()
            )
    return translation_id



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
            description=("export type parameter srt/vtt/txt/docx/docx-bilingual/sbv/TTML/scc/rt"),
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

    supported_types = ["srt", "vtt", "txt", "docx", "docx-bilingual", "scc", "sbv", "TTML", "rt"]
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
        content = convert_to_paragraph_monolingual(payload, task.video.name)
        return convert_to_docx(content)
    elif export_type == "docx-bilingual":
        filename = "translation.docx"
        content = convert_to_paragraph_bilingual(payload, task.video.name)
        return convert_to_docx(content)

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