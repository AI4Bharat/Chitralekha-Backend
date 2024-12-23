import csv
import io
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import status
from rest_framework.decorators import (
    api_view,
    permission_classes,
    authentication_classes,
)
from rest_framework.response import Response
from task.tasks import celery_nmt_tts_call
from transcript.models import Transcript
from transcript.views import get_transcript_id
from task.models import Task, TRANSLATION_VOICEOVER_EDIT
from translation.utils import get_batch_translations_using_indictrans_nmt_api
from translation.models import (
    Translation,
    TRANSLATION_EDIT_COMPLETE,
    TRANSLATION_EDIT_INPROGRESS,
)
from .metadata import (
    VOICEOVER_SUPPORTED_LANGUAGES,
    VOICEOVER_LANGUAGE_CHOICES,
    LANGUAGE_LABELS,
)
from .models import (
    VoiceOver,
    VOICEOVER_TYPE_CHOICES,
    VOICEOVER_SELECT_SOURCE,
    VOICEOVER_EDIT_INPROGRESS,
    VOICEOVER_EDIT_COMPLETE,
    VOICEOVER_REVIEW_INPROGRESS,
    VOICEOVER_REVIEW_COMPLETE,
)
from datetime import datetime, timedelta
from .utils import *
from config import voice_over_payload_offset_size, app_name
from .tasks import (
    celery_integration,
    export_voiceover_async,
    bulk_export_voiceover_async,
)
from django.db.models import Count, F, Sum
from operator import itemgetter
from itertools import groupby
from pydub import AudioSegment
import copy
import uuid
import regex
from glossary.tmx.tmxservice import TMXService
from organization.decorators import is_admin
from organization.models import Organization
from video.models import Video

@api_view(["GET"])
def get_voice_over_export_types(request):
    return Response(
        {"export_types": ["mp4", "mp3", "flac", "wav"]}, status=status.HTTP_200_OK
    )


def get_voice_over_id(task):
    voice_over = VoiceOver.objects.filter(task=task)
    if "EDIT" in task.task_type:
        if task.status == "NEW":
            voice_over_id = None
        if task.status == "SELECTED_SOURCE":
            voice_over_id = (
                voice_over.filter(video=task.video)
                .filter(status="VOICEOVER_SELECT_SOURCE")
                .first()
            )
        if task.status == "INPROGRESS":
            voice_over_id = (
                voice_over.filter(video=task.video)
                .filter(status="VOICEOVER_EDIT_INPROGRESS")
                .first()
            )
        if task.status == "POST_PROCESS":
            voice_over_id = (
                voice_over.filter(video=task.video)
                .filter(status="VOICEOVER_EDIT_INPROGRESS")
                .first()
            )
        if task.status == "COMPLETE":
            voice_over_id = (
                voice_over.filter(video=task.video)
                .filter(status="VOICEOVER_EDIT_COMPLETE")
                .first()
            )
        if task.status == "REOPEN":
            voice_over_id = (
                voice_over.filter(video=task.video)
                .filter(status="VOICEOVER_EDIT_INPROGRESS")
                .first()
            )
        if task.status == "FAILED":
            voice_over_id = (
                voice_over.filter(video=task.video)
                .filter(status="VOICEOVER_SELECT_SOURCE")
                .first()
            )
    else:
        if task.status == "NEW":
            voice_over_id = (
                voice_over.filter(video=task.video)
                .filter(status="VOICEOVER_REVIEWER_ASSIGNED")
                .first()
            )
        if task.status == "INPROGRESS":
            voice_over_id = (
                voice_over.filter(video=task.video)
                .filter(status="VOICEOVER_REVIEW_INPROGRESS")
                .first()
            )
        if task.status == "COMPLETE":
            voice_over_id = (
                voice_over.filter(video=task.video)
                .filter(status="VOICEOVER_REVIEW_COMPLETE")
                .first()
            )
    return voice_over_id


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
    responses={200: "Returns the empty audios."},
)
@api_view(["GET"])
def get_empty_audios(request):
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

    voice_over = get_voice_over_id(task)
    if voice_over is not None:
        voice_over_id = voice_over.id
    else:
        if task.status == "POST_PROCESS":
            return Response(
                {"message": "VoiceOver is in Post Process stage."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(
            {"message": "VoiceOver doesn't exist."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Retrieve the voice over object
    try:
        voice_over = VoiceOver.objects.get(pk=voice_over_id)
    except VoiceOver.DoesNotExist:
        return Response(
            {"message": "VoiceOver doesn't exist."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    empty_audios = []
    if voice_over.payload and "payload" in voice_over.payload:
        index = 0
        for sentence in voice_over.payload["payload"].values():
            data_dict = {}
            data_dict["index"] = index
            data_dict["sentence"] = sentence.get("text", "")
            data_dict["reason"] = "Audio not generated"
            data_dict["page_number"] = index / voice_over_payload_offset_size + 1
            if sentence.get("audio", "") == "":
                empty_audios.append(data_dict)
                continue
            if sentence["audio"]["audioContent"] == "":
                print(
                    "Empty audio with dict found",
                    sentence.get("audio", {}).get("audioContent", {}),
                )
                empty_audios.append(data_dict)
            index = index + 1

    if empty_audios:
        return Response(
            {
                "data": empty_audios,
                "message": "Sentences with empty audios are returned.",
            },
            status=status.HTTP_200_OK,
        )
    else:
        return Response(
            {"message": "No issues in audios."},
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
            description=("Offset number"),
            type=openapi.TYPE_INTEGER,
            required=False,
        ),
    ],
    responses={200: "Returns the Translated Audio."},
)
@api_view(["GET"])
def update_completed_count(request):
    try:
        task_id = request.query_params["task_id"]
    except KeyError:
        return Response(
            {"message": "Missing required parameters - task_id or offset"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        task = Task.objects.get(pk=task_id)
    except Task.DoesNotExist:
        return Response(
            {"message": "Task doesn't exist."},
            status=status.HTTP_404_NOT_FOUND,
        )

    voice_over = get_voice_over_id(task)
    completed_count = 0

    if voice_over is not None:
        voice_over_id = voice_over.id
    try:
        voice_over = VoiceOver.objects.get(pk=voice_over_id)
    except VoiceOver.DoesNotExist:
        return Response(
            {"message": "VoiceOver doesn't exist."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    audios_list = len(voice_over.payload["payload"])
    empty_audio_list = []
    try:
        for i in range(len(voice_over.payload["payload"]) - 1):
            if (
                "audio" in voice_over.payload["payload"][str(i)].keys()
                and voice_over.payload["payload"][str(i)]["audio"] == ""
            ):
                empty_audio_list.append(i)
            else:
                completed_count += 1
        voice_over.payload["payload"]["completed_count"] = completed_count
        voice_over.save()
    except:
        print("Error in processing")
    count = request.query_params.get("offset")
    if count != None and int(count) > 0:
        voice_over.payload["payload"]["completed_count"] = int(count)
        voice_over.save()
    return Response({"message": "Count updated."}, status=status.HTTP_200_OK)


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
            description=("Offset number"),
            type=openapi.TYPE_INTEGER,
            required=True,
        ),
    ],
    responses={200: "Returns the Translated Audio."},
)
@api_view(["GET"])
def get_payload(request):
    try:
        task_id = request.query_params["task_id"]
        offset = int(request.query_params["offset"])
    except KeyError:
        return Response(
            {"message": "Missing required parameters - task_id or offset"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        task = Task.objects.get(pk=task_id)
    except Task.DoesNotExist:
        return Response(
            {"message": "Task doesn't exist."},
            status=status.HTTP_404_NOT_FOUND,
        )

    voice_over = get_voice_over_id(task)
    if voice_over is not None:
        voice_over_id = voice_over.id
    else:
        if task.status == "POST_PROCESS":
            return Response(
                {"message": "VoiceOver is in Post Process stage."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(
            {"message": "VoiceOver doesn't exist."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Retrieve the voice over object
    try:
        voice_over = VoiceOver.objects.get(pk=voice_over_id)
    except VoiceOver.DoesNotExist:
        return Response(
            {"message": "VoiceOver doesn't exist."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    sentences_list = []
    current_offset = offset - 1
    translation_payload = []
    completed_count = 0
    if voice_over.translation:
        if voice_over.voice_over_type == "MACHINE_GENERATED":
            count_cards = len(list(voice_over.payload["payload"].keys())) - 1
        else:
            count_cards = len(voice_over.translation.payload["payload"]) - 1
        start_offset = current_offset
        end_offset = start_offset + voice_over_payload_offset_size - 1

        generate_voice_over = True
        if end_offset >= count_cards:
            next = None
            previous = offset - voice_over_payload_offset_size
        elif offset == 1:
            delete_indices = []
            for index, sentence in enumerate(voice_over.translation.payload["payload"]):
                if "text" not in sentence.keys():
                    delete_indices.append(index)
            delete_indices.reverse()
            for ind in delete_indices:
                voice_over.translation.payload["payload"].pop(ind)
            voice_over.translation.save()
            previous = None
            next = offset + voice_over_payload_offset_size
        else:
            next = offset + voice_over_payload_offset_size
            previous = offset - voice_over_payload_offset_size

        for index, translation_text in enumerate(
            voice_over.translation.payload["payload"][start_offset : end_offset + 1]
        ):
            translation_payload.append((translation_text, index))
    else:
        return Response(
            {"message": "There is no translation associated with this voice over."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if voice_over.voice_over_type == "MACHINE_GENERATED":
        input_sentences = []
        fast_audio_threshold = 20 if task.target_language != "sa" else 16
        moderate_audio_threshold = 16 if task.target_language != "sa" else 12
        for text, index in translation_payload:
            audio_index = str(start_offset + index)
            if audio_index in voice_over.payload["payload"].keys():
                start_time = voice_over.payload["payload"][str(audio_index)][
                    "start_time"
                ]
                end_time = voice_over.payload["payload"][str(audio_index)]["end_time"]
                if (
                    "transcription_text"
                    in voice_over.payload["payload"][str(audio_index)].keys()
                ):
                    transcription_text = voice_over.payload["payload"][
                        str(audio_index)
                    ]["transcription_text"]
                else:
                    transcription_text = translation_payload[index][0]["text"]
                time_difference = (
                    datetime.strptime(end_time, "%H:%M:%S.%f")
                    - timedelta(
                        hours=float(start_time.split(":")[0]),
                        minutes=float(start_time.split(":")[1]),
                        seconds=float(start_time.split(":")[-1]),
                    )
                ).strftime("%H:%M:%S.%f")
                t_d = (
                    float(time_difference.split(":")[0]) * 3600
                    + float(time_difference.split(":")[1]) * 60
                    + float(time_difference.split(":")[2])
                )
                try:
                    text_length_per_second = len(transcription_text)/t_d
                except:
                    text_length_per_second = 100
                sentences_list.append(
                    {
                        "id": str(int(audio_index) + 1),
                        "time_difference": "{:.3f}".format(t_d),
                        "start_time": start_time,
                        "end_time": end_time,
                        "text": voice_over.payload["payload"][str(audio_index)]["text"],
                        "transcription_text": transcription_text,
                        "audio": voice_over.payload["payload"][str(audio_index)][
                            "audio"
                        ],
                        "audio_speed": 1,
                        "fast_audio": 0 if text_length_per_second < moderate_audio_threshold else 1 if text_length_per_second < fast_audio_threshold else 2,
                    }
                )
        payload = {"payload": sentences_list}
    elif voice_over.voice_over_type == "MANUALLY_CREATED":
        if end_offset > count_cards:
            end_offset = end_offset - 1
        if voice_over.payload and "payload" in voice_over.payload:
            count = 0

            for i in range(start_offset, end_offset + 1):
                if str(i) in voice_over.payload["payload"].keys():
                    start_time = voice_over.payload["payload"][str(i)]["start_time"]
                    end_time = voice_over.payload["payload"][str(i)]["end_time"]
                    time_difference = (
                        datetime.strptime(end_time, "%H:%M:%S.%f")
                        - timedelta(
                            hours=float(start_time.split(":")[0]),
                            minutes=float(start_time.split(":")[1]),
                            seconds=float(start_time.split(":")[-1]),
                        )
                    ).strftime("%H:%M:%S.%f")
                    t_d = (
                        int(time_difference.split(":")[0]) * 3600
                        + int(time_difference.split(":")[1]) * 60
                        + float(time_difference.split(":")[2])
                    )
                    # if "audioContent" in voice_over.payload["payload"][str(i)]["audio"].keys():
                    #     completed_count += 1
                    sentences_list.append(
                        {
                            "audio": voice_over.payload["payload"][str(i)]["audio"],
                            "text": voice_over.payload["payload"][str(i)]["text"],
                            "start_time": voice_over.payload["payload"][str(i)][
                                "start_time"
                            ],
                            "end_time": voice_over.payload["payload"][str(i)][
                                "end_time"
                            ],
                            "time_difference": t_d,
                            "id": i + 1,
                            "audio_speed": 1,
                        }
                    )
                else:
                    start_time = voice_over.translation.payload["payload"][i][
                        "start_time"
                    ]
                    end_time = voice_over.translation.payload["payload"][i]["end_time"]
                    time_difference = (
                        datetime.strptime(end_time, "%H:%M:%S.%f")
                        - timedelta(
                            hours=float(start_time.split(":")[0]),
                            minutes=float(start_time.split(":")[1]),
                            seconds=float(start_time.split(":")[-1]),
                        )
                    ).strftime("%H:%M:%S.%f")
                    t_d = (
                        int(time_difference.split(":")[0]) * 3600
                        + int(time_difference.split(":")[1]) * 60
                        + float(time_difference.split(":")[2])
                    )
                    sentences_list.append(
                        {
                            "time_difference": t_d,
                            "start_time": start_time,
                            "end_time": end_time,
                            "text": voice_over.translation.payload["payload"][i][
                                "target_text"
                            ],
                            "audio": "",
                            "id": i + 1,
                            "audio_speed": 1,
                        }
                    )
                    count += 1
        payload = {"payload": sentences_list}
    else:
        return Response(
            {"message": "Payload not generated for voice over"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if voice_over.voice_over_type == "MANUALLY_CREATED":
        return Response(
            {
                "completed_count": voice_over.payload["payload"]["completed_count"],
                "sentences_count": len(voice_over.translation.payload["payload"]),
                "count": count_cards + 1,
                "next": next,
                "current": offset,
                "previous": previous,
                "payload": payload,
                "source_type": voice_over.voice_over_type,
            },
            status=status.HTTP_200_OK,
        )

    return Response(
        {
            "completed_count": count_cards + 1,
            "count": count_cards + 1,
            "next": next,
            "current": offset,
            "previous": previous,
            "payload": payload,
            "source_type": voice_over.voice_over_type,
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

    voice_over = get_voice_over_id(task)
    if voice_over is None:
        return Response(
            {"message": "Voiceover not found."},
            status=status.HTTP_404_NOT_FOUND,
        )
    else:
        voice_over_id = voice_over.id

    # Retrieve the transcript object
    try:
        voiceOver = VoiceOver.objects.get(pk=voice_over_id)
    except VoiceOver.DoesNotExist:
        return Response(
            {"message": "Voiceover doesn't exist."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Replace all occurrences of word_to_replace with replace_word
    for record in voiceOver.payload["payload"].values():
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

    voiceOver.save()

    return Response(
        {"message": "Voiceover updated successfully."},
        status=status.HTTP_200_OK,
    )


def change_active_status_of_next_tasks(task, target_language, voice_over_obj):
    task = (
        Task.objects.filter(video=task.video)
        .filter(target_language=target_language)
        .filter(task_type="VOICEOVER_REVIEW")
        .first()
    )
    if task:
        voice_over = (
            VoiceOver.objects.filter(video=task.video)
            .filter(target_language=target_language)
            .filter(status="VOICEOVER_REVIEWER_ASSIGNED")
            .first()
        )
        if voice_over is not None:
            task.is_active = True
            voice_over.translation = voice_over_obj.translation
            voice_over.audio = voice_over_obj.audio
            voice_over.save()
            task.save()
    else:
        print("No change in status")


@swagger_auto_schema(
    method="post",
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        required=["text", "source_language" "target_language"],
        properties={
            "text": openapi.Schema(
                type=openapi.TYPE_STRING,
                description="Text to be translated",
            ),
            "source_language": openapi.Schema(
                type=openapi.TYPE_STRING,
                description="Source Language",
            ),
            "target_language": openapi.Schema(
                type=openapi.TYPE_STRING,
                description="Target language ",
            ),
        },
        description="Post request body",
    ),
    responses={200: "Returns the translated text"},
)
@api_view(["POST"])
def get_translated_text(request):
    try:
        # Get the required data from the POST body
        text = request.data["text"]
        source_language = request.data["source_language"]
        target_language = request.data["target_language"]

    except KeyError:
        return Response(
            {"message": "Missing required parameters"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    try:
        tmxservice = TMXService()
        translated_text = get_batch_translations_using_indictrans_nmt_api(
            [text],
            source_language,
            target_language,
        )

        if type(translated_text) == list:
            locale = source_language + "|" + target_language
            user_id = str(request.user.id)
            org_id = None
            tmx_level = "USER"
            tmx_phrases, res_dict = tmxservice.get_tmx_phrases(
                user_id,
                org_id,
                locale,
                text,
                tmx_level,
            )

            (tgt, tmx_replacement,) = tmxservice.replace_nmt_tgt_with_user_tgt(
                tmx_phrases,
                text,
                translated_text[0],
            )

            if len(tmx_replacement) > 0:
                for i in range(len(tmx_replacement)):
                    translated_text[0] = translated_text[0].replace(
                        tmx_replacement[i]["tgt"],
                        tmx_replacement[i]["tmx_tgt"],
                    )
            return Response(
                {"Translated text": translated_text[0]}, status=status.HTTP_200_OK
            )
    except:
        return Response(
            {"message": "Translation failed"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
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
        404: "No voice_over found for given task",
    },
)
@api_view(["GET"])
def fetch_voice_over_status(request):
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

    voice_over = get_voice_over_id(task)
    if voice_over is not None:
        voice_over_id = voice_over.id
    try:
        voice_over = VoiceOver.objects.get(pk=voice_over_id)
        return Response(
            {
                "message": "Status has been fetched successfully",
                "task_id": task.id,
                "voiceover_id": voice_over_id,
                "status": voice_over.status,
            },
            status=status.HTTP_200_OK,
        )
    except:
        return Response(
            {"message": "VoiceOver doesn't exist."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    
@swagger_auto_schema(
    method="post",
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        required=["task_id", "vo_status"],
        properties={
            "task_id": openapi.Schema(
                type=openapi.TYPE_INTEGER,
                description="An integer identifying the voice_over instance",
            ),
            "vo_status": openapi.Schema(
                type=openapi.TYPE_STRING,
                description="Voiceover task status to be set",
            )
        },
        description="Post request body",
    ),
    responses={
        200: "Status has been updated successfully",
        400: "Bad request",
        404: "No voice_over found for given task",
    },
)
@api_view(["POST"])
def update_voice_over_status(request):
    if not request.user.is_authenticated:
        return Response({"message":"You do not have enough permissions to access this view!"}, status=401)
    try:
        # Get the required data from the POST body
        task_id = request.data["task_id"]
        vo_status = request.data["vo_status"]
    except KeyError:
        return Response(
            {
                "message": "Missing required parameters - task_id or vo_status"
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

    voice_over = get_voice_over_id(task)
    if voice_over is not None:
        voice_over_id = voice_over.id
    try:
        voice_over = VoiceOver.objects.get(pk=voice_over_id)
        if vo_status in ["VOICEOVER_SELECT_SOURCE", "VOICEOVER_EDITOR_ASSIGNED", "VOICEOVER_EDIT_INPROGRESS", "VOICEOVER_EDIT_COMPLETE", "VOICEOVER_REVIEWER_ASSIGNED", "VOICEOVER_REVIEW_INPROGRESS", "VOICEOVER_REVIEW_COMPLETE"]:
            voice_over.status = vo_status
            voice_over.save()
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
            {"message": "VoiceOver doesn't exist."},
            status=status.HTTP_400_BAD_REQUEST,
        )

@swagger_auto_schema(
    method="post",
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        required=["task_id", "payload", "offset"],
        properties={
            "task_id": openapi.Schema(
                type=openapi.TYPE_INTEGER,
                description="An integer identifying the voice_over instance",
            ),
            "payload": openapi.Schema(
                type=openapi.TYPE_OBJECT,
                description="An audio file ",
            ),
            "offset": openapi.Schema(
                type=openapi.TYPE_INTEGER,
                description="offset",
            ),
        },
        description="Post request body",
    ),
    responses={
        200: "VoiceOver has been created/updated successfully",
        400: "Bad request",
        404: "No voice_over found for given task",
    },
)
@api_view(["POST"])
def save_voice_over(request):
    try:
        # Get the required data from the POST body
        voice_over_id = request.data.get("voice_over_id", None)
        payload = request.data["payload"]
        task_id = request.data["task_id"]
        offset = request.data["offset"]

    except KeyError:
        return Response(
            {
                "message": "Missing required parameters - language or payload or task_id or voice_over_id"
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

    completed_count = 0
    voice_over = get_voice_over_id(task)
    if voice_over is not None:
        voice_over_id = voice_over.id
    else:
        if task.status == "POST_PROCESS":
            return Response(
                {"message": "VoiceOver is in Post Process stage."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        print("Here")
        return Response(
            {"message": "VoiceOver doesn't exist."},
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
        voice_over = VoiceOver.objects.get(pk=voice_over_id)
        target_language = voice_over.target_language
        translation = voice_over.translation

        if (
            task.task_type == TRANSLATION_VOICEOVER_EDIT
            and request.data.get("final")
            and Translation.objects.filter(
                task=task, status=TRANSLATION_EDIT_COMPLETE
            ).first()
            == None
        ):
            inprogress_translation = Translation.objects.filter(
                task=task, status=TRANSLATION_EDIT_INPROGRESS
            ).first()
            complete_translation = copy.deepcopy(translation)
            complete_translation.translation_uuid = uuid.uuid4()
            complete_translation.status = TRANSLATION_EDIT_COMPLETE
            complete_translation.id = None  # Reset the ID to create a new instance
            complete_translation.parent = inprogress_translation
            complete_translation.save()
            if (
                complete_translation.payload != ""
                and complete_translation.payload is not None
            ):
                num_words = 0
                for idv_translation in complete_translation.payload["payload"]:
                    if "target_text" in idv_translation.keys():
                        cleaned_text = regex.sub(
                            r"[^\p{L}\s]", "", idv_translation["target_text"]
                        ).lower()  # for removing special characters
                        cleaned_text = regex.sub(
                            r"\s+", " ", cleaned_text
                        )  # for removing multiple blank spaces
                        num_words += len(cleaned_text.split(" "))
                complete_translation.payload["word_count"] = num_words
                complete_translation.save()
                voice_over.translation = complete_translation
                voice_over.save()
            else:
                complete_translation.payload = {"payload": [], "word_count": 0}
                complete_translation.save()
                voice_over.translation = complete_translation
                voice_over.save()
            translation = complete_translation
            print("Saved Complete Translation with inprogress", inprogress_translation)
        else:
            inprogress_translation = Translation.objects.filter(
                task=task, status=TRANSLATION_EDIT_INPROGRESS
            ).first()
            if (
                task.task_type == TRANSLATION_VOICEOVER_EDIT
                and inprogress_translation == None
            ):
                inprogress_translation = copy.deepcopy(translation)
                inprogress_translation.translation_uuid = uuid.uuid4()
                inprogress_translation.status = TRANSLATION_EDIT_INPROGRESS
                inprogress_translation.id = (
                    None  # Reset the ID to create a new instance
                )
                inprogress_translation.parent = translation
                inprogress_translation.save()
                voice_over.translation = inprogress_translation
                voice_over.save()
                print("Saved IP Translation with inprogress")
                translation = inprogress_translation
        # Check if the transcript has a user
        if task.user == request.user:
            return Response(
                {"message": "You are not allowed to update this voice_over."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        else:
            if voice_over.status == VOICEOVER_REVIEW_COMPLETE:
                return Response(
                    {
                        "message": "VoiceOver can't be edited, as the final voice_over already exists"
                    },
                    status=status.HTTP_201_CREATED,
                )
            # if task.status == "POST_PROCESS":
            #     return Response(
            #         {"message": "Voice Over is in Post Process stage."},
            #         status=status.HTTP_400_BAD_REQUEST,
            #     )

            if voice_over.voice_over_type == "MACHINE_GENERATED":
                try:
                    count_cards = len(list(voice_over.payload["payload"].keys())) - 1
                except:
                    count_cards = (
                        len(list(json.loads(voice_over.payload["payload"]).keys())) - 1
                    )
            else:
                count_cards = len(voice_over.translation.payload["payload"]) - 1
            current_offset = offset - 1
            start_offset = current_offset
            end_offset = start_offset + voice_over_payload_offset_size - 1

            if end_offset >= count_cards:
                next = None
                previous = offset - voice_over_payload_offset_size
            elif offset == 1:
                previous = None
                next = offset + voice_over_payload_offset_size
            else:
                next = offset + voice_over_payload_offset_size
                previous = offset - voice_over_payload_offset_size

            sentences_list = []
            if "EDIT" in task.task_type:
                translation_payload = []
                for index, voice_over_payload in enumerate(payload["payload"]):
                    start_time = voice_over_payload["start_time"]
                    end_time = voice_over_payload["end_time"]
                    if (
                        voice_over_payload["transcription_text"] == ""
                        or len(voice_over_payload["transcription_text"]) == 0
                    ):
                        return Response(
                            {"message": "Transcript can't be empty."},
                            status=status.HTTP_400_BAD_REQUEST,
                        )
                    if (
                        "retranslate" in voice_over_payload
                        and voice_over_payload["retranslate"] == True
                    ):
                        tmxservice = TMXService()
                        translated_text = (
                            get_batch_translations_using_indictrans_nmt_api(
                                [voice_over_payload["transcription_text"]],
                                translation.video.language,
                                translation.task.target_language,
                            )
                        )

                        if type(translated_text) == list:
                            voice_over_payload["text"] = translated_text[0]
                            locale = (
                                LANGUAGE_LABELS[task.get_src_language_label]
                                + "|"
                                + voice_over.target_language
                            )
                            user_id = str(user.id)
                            org_id = None
                            tmx_level = "USER"
                            tmx_phrases, res_dict = tmxservice.get_tmx_phrases(
                                user_id,
                                org_id,
                                locale,
                                voice_over_payload["transcription_text"],
                                tmx_level,
                            )

                            (
                                tgt,
                                tmx_replacement,
                            ) = tmxservice.replace_nmt_tgt_with_user_tgt(
                                tmx_phrases,
                                voice_over_payload["transcription_text"],
                                voice_over_payload["text"],
                            )

                            if len(tmx_replacement) > 0:
                                for i in range(len(tmx_replacement)):
                                    voice_over_payload["text"] = voice_over_payload[
                                        "text"
                                    ].replace(
                                        tmx_replacement[i]["tgt"],
                                        tmx_replacement[i]["tmx_tgt"],
                                    )
                        else:
                            logging.info(
                                "Failed to retranslate for task_id %s",
                                str(translation.task.id),
                            )
                    text = voice_over_payload["text"]
                    if text == "" or len(text) == 0:
                        return Response(
                            {"message": "Text can't be empty for segment "+str(index+1)},
                            status=status.HTTP_400_BAD_REQUEST,
                        )

                    original_duration = get_original_duration(start_time, end_time)

                    if (
                        voice_over.voice_over_type == "MACHINE_GENERATED"
                        and "text_changed" in voice_over_payload
                        and voice_over_payload["text_changed"] == True
                    ):
                        translation_payload.append(
                            (voice_over_payload["text"], "", True, original_duration)
                        )
                    elif voice_over.voice_over_type == "MANUALLY_CREATED":
                        translation_payload.append(
                            (
                                voice_over_payload["text"],
                                voice_over_payload["audio"],
                                original_duration,
                            )
                        )
                    else:
                        translation_payload.append(
                            (
                                voice_over_payload["text"],
                                voice_over_payload["audio"],
                                False,
                                original_duration,
                            )
                        )

                if voice_over.voice_over_type == "MANUALLY_CREATED":
                    voiceover_adjusted = adjust_voiceover(translation_payload)
                else:
                    try:
                        voiceover_machine_generated = generate_voiceover_payload(
                            translation_payload, task.target_language, task
                        )
                    except ZeroDivisionError:
                        return Response(
                            {"message": "Cannot generate voiceover due to 0 duration for a segment"},
                            status=status.HTTP_400_BAD_REQUEST,
                        )
                if request.data.get("final"):
                    if (
                        VoiceOver.objects.filter(status=VOICEOVER_EDIT_COMPLETE)
                        .filter(target_language=target_language)
                        .filter(translation=translation)
                        .first()
                        is not None
                    ):
                        return Response(
                            {"message": "Voice Over Edit already exists."},
                            status=status.HTTP_201_CREATED,
                        )
                    else:
                        voice_over_obj_inprogress = (
                            VoiceOver.objects.filter(status=VOICEOVER_EDIT_INPROGRESS)
                            .filter(target_language=target_language)
                            .filter(translation=translation)
                            .first()
                        )
                        if voice_over_obj_inprogress is None:
                            voice_over_obj_selected = (
                                VoiceOver.objects.filter(status=VOICEOVER_SELECT_SOURCE)
                                .filter(target_language=target_language)
                                .filter(translation=translation)
                                .first()
                            )
                            voice_over_obj = voice_over_obj_selected
                        else:
                            voice_over_obj = voice_over_obj_inprogress
                        ts_status = VOICEOVER_EDIT_INPROGRESS
                        voice_over_type = voice_over.voice_over_type
                        if int(payload["payload"][0]["id"]) == int(offset):
                            for i in range(len(payload["payload"])):
                                start_time = payload["payload"][i]["start_time"]
                                end_time = payload["payload"][i]["end_time"]
                                transcription_text = payload["payload"][i][
                                    "transcription_text"
                                ]
                                time_difference = (
                                    datetime.strptime(end_time, "%H:%M:%S.%f")
                                    - timedelta(
                                        hours=float(start_time.split(":")[0]),
                                        minutes=float(start_time.split(":")[1]),
                                        seconds=float(start_time.split(":")[-1]),
                                    )
                                ).strftime("%H:%M:%S.%f")
                                t_d = (
                                    int(time_difference.split(":")[0]) * 3600
                                    + int(time_difference.split(":")[1]) * 60
                                    + float(time_difference.split(":")[2])
                                )
                                if voice_over_obj.voice_over_type == "MANUALLY_CREATED":
                                    if (
                                        type(voiceover_adjusted[i][1]) == dict
                                        and "audioContent"
                                        in voiceover_adjusted[i][1].keys()
                                        and len(
                                            voiceover_adjusted[i][1]["audioContent"]
                                        )
                                        > 400
                                    ):
                                        if (
                                            str(start_offset + i)
                                            not in voice_over_obj.payload[
                                                "payload"
                                            ].keys()
                                        ):
                                            voice_over_obj.payload["payload"][
                                                "completed_count"
                                            ] += 1

                                        elif (
                                            str(start_offset + i)
                                            in voice_over_obj.payload["payload"].keys()
                                            and "audio"
                                            in voice_over_obj.payload["payload"][
                                                str(start_offset + i)
                                            ].keys()
                                            and type(
                                                voice_over_obj.payload["payload"][
                                                    str(start_offset + i)
                                                ]
                                            )
                                            == dict
                                            and "audioContent"
                                            not in voice_over_obj.payload["payload"][
                                                str(start_offset + i)
                                            ]["audio"]
                                        ):
                                            voice_over_obj.payload["payload"][
                                                "completed_count"
                                            ] += 1
                                        completed_count = voice_over_obj.payload[
                                            "payload"
                                        ]["completed_count"]
                                else:
                                    completed_count = count_cards
                                if (
                                    str(start_offset + i)
                                    in voice_over_obj.payload["payload"].keys()
                                    and voice_over_obj.voice_over_type
                                    == "MANUALLY_CREATED"
                                ):
                                    if voiceover_adjusted[i][1] == dict:
                                        voice_over_obj.payload["payload"][
                                            str(start_offset + i)
                                        ] = {
                                            "time_difference": t_d,
                                            "start_time": payload["payload"][i][
                                                "start_time"
                                            ],
                                            "end_time": payload["payload"][i][
                                                "end_time"
                                            ],
                                            "text": payload["payload"][i]["text"],
                                            "audio": voiceover_adjusted[i][1],
                                            "audio_speed": 1,
                                        }
                                        sentences_list.append(
                                            {
                                                "id": start_offset + i + 1,
                                                "time_difference": t_d,
                                                "start_time": payload["payload"][i][
                                                    "start_time"
                                                ],
                                                "end_time": payload["payload"][i][
                                                    "end_time"
                                                ],
                                                "text": payload["payload"][i]["text"],
                                                "audio": voiceover_adjusted[i][1],
                                                "audio_speed": 1,
                                                "transcription_text": transcription_text,
                                            }
                                        )
                                else:
                                    voice_over_obj.payload["payload"][
                                        str(start_offset + i)
                                    ] = {
                                        "time_difference": t_d,
                                        "start_time": payload["payload"][i][
                                            "start_time"
                                        ],
                                        "end_time": payload["payload"][i]["end_time"],
                                        "text": payload["payload"][i]["text"],
                                        "audio": voiceover_machine_generated[i][1],
                                        "audio_speed": 1,
                                        "transcription_text": payload["payload"][i][
                                            "transcription_text"
                                        ],
                                    }
                                    sentences_list.append(
                                        {
                                            "id": start_offset + i + 1,
                                            "time_difference": t_d,
                                            "start_time": payload["payload"][i][
                                                "start_time"
                                            ],
                                            "end_time": payload["payload"][i][
                                                "end_time"
                                            ],
                                            "text": payload["payload"][i]["text"],
                                            "audio": voiceover_machine_generated[i][1],
                                            "audio_speed": 1,
                                            "transcription_text": payload["payload"][i][
                                                "transcription_text"
                                            ],
                                        }
                                    )
                                voice_over_obj.save()

                        # delete inprogress payload
                        missing_cards = check_audio_completion(voice_over_obj)
                        # missing_cards = []
                        if len(missing_cards) > 0:
                            return Response(
                                {
                                    "message": "Voice Over can't be saved as there are following issues.",
                                    "missing_cards_info": missing_cards,
                                },
                                status=status.HTTP_400_BAD_REQUEST,
                            )
                        if voice_over_obj.voice_over_type == "MANUALLY_CREATED":
                            del voice_over_obj.payload["payload"]["completed_count"]
                            voice_over_obj.save()
                        file_name = voice_over_obj.video.name
                        time_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                        file_name = "{}_Video_{}_{}_{}".format(
                            app_name,
                            voice_over_obj.video.id,
                            voice_over_obj.task.id,
                            voice_over_obj.target_language,
                        )
                        # file_name = "{}_Video_{}_{}_{}".format(
                        #     app_name,
                        #     voice_over_obj.video.id,
                        #     voice_over_obj.task.id
                        #     voice_over_obj.target_language,
                        # )
                        file_path = "temporary_video_audio_storage"
                        # task.status = "POST_PROCESS"
                        task.save()
                        logging.info("Calling Async Celery Integration")
                        celery_integration(
                            file_path + "/" + file_name,
                            voice_over_obj.id,
                            voice_over_obj.video.id,
                            task.id,
                        )
                else:
                    voice_over_obj = (
                        VoiceOver.objects.filter(status=VOICEOVER_EDIT_INPROGRESS)
                        .filter(target_language=target_language)
                        .filter(translation=translation)
                        .first()
                    )
                    voice_over_type = voice_over.voice_over_type
                    if voice_over_obj is not None and int(
                        payload["payload"][0]["id"]
                    ) == int(offset):
                        fast_audio_threshold = 20 if task.target_language != "sa" else 16
                        moderate_audio_threshold = 16 if task.target_language != "sa" else 12
                        for i in range(len(payload["payload"])):
                            start_time = payload["payload"][i]["start_time"]
                            end_time = payload["payload"][i]["end_time"]
                            transcription_text = payload["payload"][i][
                                "transcription_text"
                            ]
                            time_difference = (
                                datetime.strptime(end_time, "%H:%M:%S.%f")
                                - timedelta(
                                    hours=float(start_time.split(":")[0]),
                                    minutes=float(start_time.split(":")[1]),
                                    seconds=float(start_time.split(":")[-1]),
                                )
                            ).strftime("%H:%M:%S.%f")
                            t_d = (
                                int(time_difference.split(":")[0]) * 3600
                                + int(time_difference.split(":")[1]) * 60
                                + float(time_difference.split(":")[2])
                            )
                            if voice_over_obj.voice_over_type == "MANUALLY_CREATED":
                                if (
                                    type(voiceover_adjusted[i][1]) == dict
                                    and "audioContent"
                                    in voiceover_adjusted[i][1].keys()
                                    and len(voiceover_adjusted[i][1]["audioContent"])
                                    > 0
                                ):
                                    if (
                                        str(start_offset + i)
                                        not in voice_over_obj.payload["payload"].keys()
                                    ):
                                        voice_over_obj.payload["payload"][
                                            "completed_count"
                                        ] += 1

                                    elif (
                                        str(start_offset + i)
                                        in voice_over_obj.payload["payload"].keys()
                                        and "audio"
                                        in voice_over_obj.payload["payload"][
                                            str(start_offset + i)
                                        ].keys()
                                        and type(
                                            voice_over_obj.payload["payload"][
                                                str(start_offset + i)
                                            ]
                                        )
                                        == dict
                                        and "audioContent"
                                        not in voice_over_obj.payload["payload"][
                                            str(start_offset + i)
                                        ]["audio"]
                                    ):
                                        voice_over_obj.payload["payload"][
                                            "completed_count"
                                        ] += 1
                                    completed_count = voice_over_obj.payload["payload"][
                                        "completed_count"
                                    ]
                            else:
                                completed_count = count_cards
                            if voice_over_obj.voice_over_type == "MANUALLY_CREATED":
                                voice_over_obj.payload["payload"][
                                    str(start_offset + i)
                                ] = {
                                    "time_difference": t_d,
                                    "start_time": payload["payload"][i]["start_time"],
                                    "end_time": payload["payload"][i]["end_time"],
                                    "text": payload["payload"][i]["text"],
                                    "audio": voiceover_adjusted[i][1],
                                    "audio_speed": 1,
                                }
                                sentences_list.append(
                                    {
                                        "id": start_offset + i + 1,
                                        "time_difference": t_d,
                                        "start_time": payload["payload"][i][
                                            "start_time"
                                        ],
                                        "end_time": payload["payload"][i]["end_time"],
                                        "text": payload["payload"][i]["text"],
                                        "audio": voiceover_adjusted[i][1],
                                        "audio_speed": 1,
                                        "transcription_text": transcription_text,
                                    }
                                )
                            else:
                                try:
                                    text_length_per_second = len(transcription_text)/t_d
                                except:
                                    text_length_per_second = 100
                                voice_over_obj.payload["payload"][
                                    str(start_offset + i)
                                ] = {
                                    "time_difference": t_d,
                                    "start_time": payload["payload"][i]["start_time"],
                                    "end_time": payload["payload"][i]["end_time"],
                                    "text": payload["payload"][i]["text"],
                                    "audio": (
                                        voiceover_machine_generated[i][1]
                                        if voiceover_machine_generated[i][1] != ""
                                        else voice_over_obj.payload["payload"][
                                            str(start_offset + i)
                                        ]["audio"]
                                    ),
                                    "audio_speed": 1,
                                    "transcription_text": payload["payload"][i][
                                        "transcription_text"
                                    ],
                                }
                                sentences_list.append(
                                    {
                                        "id": start_offset + i + 1,
                                        "time_difference": t_d,
                                        "start_time": payload["payload"][i][
                                            "start_time"
                                        ],
                                        "end_time": payload["payload"][i]["end_time"],
                                        "text": payload["payload"][i]["text"],
                                        "audio": (
                                            voiceover_machine_generated[i][1]
                                            if voiceover_machine_generated[i][1] != ""
                                            else voice_over_obj.payload["payload"][
                                                str(start_offset + i)
                                            ]["audio"]
                                        ),
                                        "audio_speed": 1,
                                        "transcription_text": payload["payload"][i][
                                            "transcription_text"
                                        ],
                                        "fast_audio": 0 if text_length_per_second < moderate_audio_threshold else 1 if text_length_per_second < fast_audio_threshold else 2,
                                    }
                                )
                        voice_over_obj.save()
                    else:
                        voice_over_obj = (
                            VoiceOver.objects.filter(status=VOICEOVER_SELECT_SOURCE)
                            .filter(target_language=target_language)
                            .filter(translation=translation)
                            .first()
                        )
                        if voice_over_obj is None:
                            return Response(
                                {"message": "VoiceOver object does not exist."},
                                status=status.HTTP_404_NOT_FOUND,
                            )
                        ts_status = VOICEOVER_EDIT_INPROGRESS
                        for i in range(len(payload["payload"])):
                            start_time = payload["payload"][i]["start_time"]
                            end_time = payload["payload"][i]["end_time"]
                            time_difference = (
                                datetime.strptime(end_time, "%H:%M:%S.%f")
                                - timedelta(
                                    hours=float(start_time.split(":")[0]),
                                    minutes=float(start_time.split(":")[1]),
                                    seconds=float(start_time.split(":")[-1]),
                                )
                            ).strftime("%H:%M:%S.%f")
                            t_d = (
                                int(time_difference.split(":")[0]) * 3600
                                + int(time_difference.split(":")[1]) * 60
                                + float(time_difference.split(":")[2])
                            )
                            if voice_over_obj.voice_over_type == "MANUALLY_CREATED":
                                if (
                                    type(voiceover_adjusted[i][1]) == dict
                                    and "audioContent"
                                    in voiceover_adjusted[i][1].keys()
                                    and len(voiceover_adjusted[i][1]["audioContent"])
                                    > 0
                                ):
                                    if (
                                        str(start_offset + i)
                                        not in voice_over_obj.payload["payload"].keys()
                                    ):
                                        voice_over_obj.payload["payload"][
                                            "completed_count"
                                        ] += 1

                                    elif (
                                        str(start_offset + i)
                                        in voice_over_obj.payload["payload"].keys()
                                        and "audio"
                                        in voice_over_obj.payload["payload"][
                                            str(start_offset + i)
                                        ].keys()
                                        and type(
                                            voice_over_obj.payload["payload"][
                                                str(start_offset + i)
                                            ]
                                        )
                                        == dict
                                        and "audioContent"
                                        not in voice_over_obj.payload["payload"][
                                            str(start_offset + i)
                                        ]["audio"]
                                    ):
                                        voice_over_obj.payload["payload"][
                                            "completed_count"
                                        ] += 1
                                    completed_count = voice_over_obj.payload["payload"][
                                        "completed_count"
                                    ]
                            else:
                                completed_count = count_cards
                            if voice_over.voice_over_type == "MANUALLY_CREATED":
                                voice_over_obj.payload["payload"][
                                    str(start_offset + i)
                                ] = {
                                    "time_difference": t_d,
                                    "start_time": payload["payload"][i]["start_time"],
                                    "end_time": payload["payload"][i]["end_time"],
                                    "text": payload["payload"][i]["text"],
                                    "audio": voiceover_adjusted[i][1],
                                    "audio_speed": 1,
                                }
                                sentences_list.append(
                                    {
                                        "id": start_offset + i + 1,
                                        "time_difference": t_d,
                                        "start_time": payload["payload"][i][
                                            "start_time"
                                        ],
                                        "end_time": payload["payload"][i]["end_time"],
                                        "text": payload["payload"][i]["text"],
                                        "audio": voiceover_adjusted[i][1],
                                        "audio_speed": 1,
                                    }
                                )
                            else:
                                voice_over_obj.payload["payload"][
                                    str(start_offset + i)
                                ] = {
                                    "time_difference": t_d,
                                    "start_time": payload["payload"][i]["start_time"],
                                    "end_time": payload["payload"][i]["end_time"],
                                    "text": payload["payload"][i]["text"],
                                    "audio": voiceover_machine_generated[i][1],
                                    "audio_speed": 1,
                                    "transcription_text": payload["payload"][i][
                                        "transcription_text"
                                    ],
                                }
                                sentences_list.append(
                                    {
                                        "id": start_offset + i + 1,
                                        "time_difference": t_d,
                                        "start_time": payload["payload"][i][
                                            "start_time"
                                        ],
                                        "end_time": payload["payload"][i]["end_time"],
                                        "text": payload["payload"][i]["text"],
                                        "audio": voiceover_machine_generated[i][1],
                                        "audio_speed": 1,
                                        "transcription_text": payload["payload"][i][
                                            "transcription_text"
                                        ],
                                    }
                                )

                        voice_over_obj.status = VOICEOVER_EDIT_INPROGRESS
                        voice_over_obj.save()
                        task.status = "INPROGRESS"
                        task.save()
            else:
                if request.data.get("final"):
                    if (
                        VoiceOver.objects.filter(status=VOICEOVER_REVIEW_COMPLETE)
                        .filter(target_language=target_language)
                        .filter(transcript=transcript)
                        .first()
                        is not None
                    ):
                        return Response(
                            {"message": "Reviewed Voice Over already exists."},
                            status=status.HTTP_201_CREATED,
                        )
                    ts_status = VOICEOVER_REVIEW_COMPLETE
                    voice_over_obj = VoiceOver.objects.create(
                        voice_over_type=voice_over.voice_over_type,
                        parent=voice_over,
                        translation=voice_over.translation,
                        video=voice_over.video,
                        target_language=voice_over.target_language,
                        user=user,
                        payload=payload,
                        status=ts_status,
                        task=task,
                    )
                    task.status = "COMPLETE"
                    task.save()
                else:
                    voice_over_obj = (
                        VoiceOver.objects.filter(status=VOICEOVER_REVIEW_INPROGRESS)
                        .filter(target_language=target_language)
                        .filter(translation=translation)
                        .first()
                    )
                    ts_status = VOICEOVER_REVIEW_INPROGRESS
                    voice_over_type = voice_over.voice_over_type
                    if voice_over_obj is not None:
                        voice_over_obj.payload = payload
                        voice_over_obj.voice_over_type = voice_over_type
                        voice_over_obj.save()
                        task.status = "INPROGRESS"
                        task.save()
                    else:
                        ts_status = VOICEOVER_REVIEW_INPROGRESS
                        voice_over_obj = VoiceOver.objects.create(
                            voice_over_type=voice_over.voice_over_type,
                            parent=voice_over,
                            translation=voice_over.translation,
                            video=voice_over.video,
                            target_language=voice_over.target_language,
                            user=user,
                            payload=payload,
                            status=ts_status,
                            task=task,
                        )
                        task.status = "INPROGRESS"
                        task.save()

            if (
                task.task_type == TRANSLATION_VOICEOVER_EDIT
                and request.data.get("final")
                and Translation.objects.filter(
                    task=task, status=TRANSLATION_EDIT_COMPLETE
                ).first()
                == None
            ):
                inprogress_translation = Translation.objects.filter(
                    task=task, status=TRANSLATION_EDIT_INPROGRESS
                ).first()
                complete_translation = copy.deepcopy(translation)
                complete_translation.translation_uuid = uuid.uuid4()
                complete_translation.status = TRANSLATION_EDIT_COMPLETE
                complete_translation.id = None  # Reset the ID to create a new instance
                complete_translation.parent = inprogress_translation
                complete_translation.save()
                voice_over_obj.translation = complete_translation
                voice_over_obj.status = VOICEOVER_EDIT_COMPLETE
                voice_over_obj.save()
                translation = complete_translation
                print(
                    "Saved Complete Translation with inprogress", inprogress_translation
                )
            else:
                inprogress_translation = Translation.objects.filter(
                    task=task, status=TRANSLATION_EDIT_INPROGRESS
                ).first()
                if (
                    task.task_type == TRANSLATION_VOICEOVER_EDIT
                    and inprogress_translation == None
                ):
                    inprogress_translation = copy.deepcopy(translation)
                    inprogress_translation.translation_uuid = uuid.uuid4()
                    inprogress_translation.status = TRANSLATION_EDIT_INPROGRESS
                    inprogress_translation.id = (
                        None  # Reset the ID to create a new instance
                    )
                    inprogress_translation.parent = translation
                    inprogress_translation.save()
                    voice_over_obj.translation = inprogress_translation
                    voice_over_obj.save()
                    translation = inprogress_translation
            if request.data.get("final"):
                return Response(
                    {
                        "message": "VoiceOver updated successfully.",
                        "task_id": task.id,
                        "voice_over_id": voice_over_obj.id,
                    },
                    status=status.HTTP_200_OK,
                )
            else:
                return Response(
                    {
                        "completed_count": completed_count + 1,
                        "count": count_cards + 1,
                        "next": next,
                        "current": offset,
                        "previous": previous,
                        "source_type": voice_over.voice_over_type,
                        "message": "Saved as draft.",
                        "task_id": task.id,
                        "voice_over_id": voice_over_obj.id,
                        "payload": {"payload": sentences_list},
                    },
                    status=status.HTTP_200_OK,
                )
    except VoiceOver.DoesNotExist:
        print("Exception")
        return Response(
            {"message": "VoiceOver doesn't exist."},
            status=status.HTTP_400_BAD_REQUEST,
        )


@api_view(["GET"])
@authentication_classes([])
@permission_classes([])
def get_voiceover_supported_languages(request):
    """
    Endpoint to get the supported languages for TTS API
    """
    return Response(
        [
            {"label": label, "value": value}
            for label, value in VOICEOVER_SUPPORTED_LANGUAGES.items()
        ],
        status=status.HTTP_200_OK,
    )


@api_view(["GET"])
def get_voice_over_types(request):
    """
    Fetches all voice_over types.
    """
    data = [
        {"label": voice_over_type[1], "value": voice_over_type[0]}
        for voice_over_type in VOICEOVER_TYPE_CHOICES
    ]
    return Response(data, status=status.HTTP_200_OK)


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
            description=("export type parameter mp4/mp3/flac/wav"),
            type=openapi.TYPE_STRING,
            required=True,
        ),
        openapi.Parameter(
            "bg_music",
            openapi.IN_QUERY,
            description=("export type parameter true/false"),
            type=openapi.TYPE_BOOLEAN,
            required=True,
        ),
    ],
    responses={200: "VO is exported"},
)
@api_view(["GET"])
def export_voiceover(request):
    task_id = request.query_params.get("task_id")
    export_type = request.query_params.get("export_type")
    bg_music = request.query_params.get("bg_music")
    if task_id is None:
        return Response(
            {"message": "missing param : task_id"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        task = Task.objects.get(pk=task_id)
    except Task.DoesNotExist:
        return Response(
            {"message": "Task not found."},
            status=status.HTTP_404_NOT_FOUND,
        )
    video_name = task.video.name
    voice_over = get_voice_over_id(task)

    if voice_over is not None:
        voice_over = voice_over
    else:
        if task.status == "POST_PROCESS":
            return Response(
                {"message": "VoiceOver is in Post Process stage."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(
            {"message": "VoiceOver doesn't exist."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if export_type == "mp4":
        if voice_over.azure_url == None:
            return Response(
                {"message": "Video was not created for this Voice Over Task."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(
            {
                "azure_url": voice_over.azure_url,
            },
            status=status.HTTP_200_OK,
        )
    elif export_type in ["mp3", "flac", "wav"]:
        if voice_over.azure_url_audio == None:
            return Response(
                {"message": "Audio was not created for this Voice Over Task."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        elif bg_music == "true":
            export_voiceover_async.delay(
                voice_over.task.id, export_type, request.user.id, bg_music
            )
            return Response(
                {"message": "Please wait. The audio link will be emailed to you."},
                status=status.HTTP_200_OK,
            )

        elif export_type == "flac":
            if (
                task.video.project_id.organization_id.id == 16
                and len(task.video.description) > 0
            ):
                return Response(
                    {
                        "azure_url": voice_over.azure_url_audio,
                        "video_name": task.video.description,
                    },
                    status=status.HTTP_200_OK,
                )

            else:
                return Response(
                    {"azure_url": voice_over.azure_url_audio}, status=status.HTTP_200_OK
                )
        elif export_type == "mp3":
            logging.info(
                "Downloading audio from Azure Blob %s", voice_over.azure_url_audio
            )
            export_voiceover_async.delay(
                voice_over.task.id, export_type, request.user.id, bg_music
            )
            return Response(
                {"message": "Please wait. The audio link will be emailed to you."},
                status=status.HTTP_200_OK,
            )
        elif export_type == "wav":
            export_voiceover_async.delay(
                voice_over.task.id, export_type, request.user.id, bg_music
            )
            return Response(
                {"message": "Please wait. The audio link will be emailed to you."},
                status=status.HTTP_200_OK,
            )
    else:
        return Response(
            {"message": "The supported formats are : {mp4, mp3, flac, wav} "},
            status=status.HTTP_404_NOT_FOUND,
        )


@swagger_auto_schema(
    method="get",
    manual_parameters=[
        openapi.Parameter(
            "task_ids",
            openapi.IN_QUERY,
            description=("Comma-separated list of task IDs to export"),
            type=openapi.TYPE_STRING,
            required=True,
        )
    ],
    responses={200: "VO is exported"},
)
@api_view(["GET"])
def bulk_export_voiceover(request):
    audio_size = 0
    task_ids = request.query_params.get("task_ids").split(",")
    if len(task_ids) > 10:
        return Response(
            {"message": "Exceeded maximum allowed task_ids. Maximum is 10."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    messages = []

    for task_id in task_ids:
        if task_id is None:
            messages.append({"message": "missing param : task_id"})
            continue

        try:
            task = Task.objects.get(pk=task_id)
        except Task.DoesNotExist:
            messages.append({"message": f"Task with ID:{task_id} not found."})
            continue

        voice_over = get_voice_over_id(task)
        if voice_over is not None:
            voice_over = voice_over
        else:
            if task.status == "POST_PROCESS":
                messages.append(
                    {"message": f"VoiceOver of ID:{task_id} is in Post Process stage."}
                )
                continue
            messages.append({"message": f"VoiceOver of ID:{task_id} doesn't exist."})
            continue

        if voice_over.azure_url_audio == None:
            messages.append(
                {"message": f"Audio was not created for ID:{task_id} Voice Over Task."}
            )
        else:
            audio_size += asizeof(voice_over.azure_url_audio)

    if audio_size > 1024**3:
        return Response(
            {"message": "Total size of audio files exceeds 1 GB."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if messages == []:
        bulk_export_voiceover_async.delay(task_ids, request.user.id)
        return Response(
            {"message": "The audio link will be emailed to you."},
            status=status.HTTP_200_OK,
        )
    else:
        return Response(messages, status=status.HTTP_400_BAD_REQUEST)


@api_view(["GET"])
def get_voice_over_task_counts(request):
    response = []
    tasks_in_post_process = Task.objects.filter(status="POST_PROCESS").all()
    all_voice_over_tasks = Task.objects.filter(task_type="VOICEOVER_EDIT").all()
    if len(list(tasks_in_post_process)) > 0:
        for task in tasks_in_post_process:
            response.append(
                {
                    "stage": "post process",
                    "task_id": task.id,
                    "video_id": task.video.id,
                    "video": task.video.name,
                }
            )
    if len(list(all_voice_over_tasks)) > 0:
        for task in all_voice_over_tasks:
            response.append(
                {
                    "task_id": task.id,
                    "video_id": task.video.id,
                    "video": task.video.name,
                    "status": task.status,
                    "active": task.is_active,
                }
            )
    return Response(
        response,
        status=status.HTTP_200_OK,
    )


@api_view(["GET"])
def get_voiceover_report(request):
    voiceovers = VoiceOver.objects.filter(status="VOICEOVER_EDIT_COMPLETE").values(
        "video__project_id__organization_id__title",
        src_language=F("video__language"),
        tgt_language=F("target_language"),
    )
    voiceover_statistics = (
        voiceovers.annotate(voiceovers_completed=Count("id"))
        .annotate(voiceover_duration=Sum(F("video__duration")))
        .order_by("-voiceover_duration")
    )
    voiceover_data = []
    for elem in voiceover_statistics:
        voiceover_dict = {
            "org": elem["video__project_id__organization_id__title"],
            "src_language": {
                "value": dict(VOICEOVER_LANGUAGE_CHOICES)[elem["src_language"]],
                "label": "Source Langauge",
            },
            "tgt_language": {
                "value": dict(VOICEOVER_LANGUAGE_CHOICES)[elem["tgt_language"]],
                "label": "Target Language",
            },
            "voiceover_duration": {
                "value": round(elem["voiceover_duration"].total_seconds() / 3600, 3),
                "label": "VoiceOver Duration (Hours)",
            },
            "voiceovers_completed": {
                "value": elem["voiceovers_completed"],
                "label": "VoiceOver Tasks Count",
            },
        }
        voiceover_data.append(voiceover_dict)
    voiceover_data.sort(key=itemgetter("org"))
    res = []
    for org, items in groupby(voiceover_data, key=itemgetter("org")):
        lang_data = []
        for i in items:
            del i["org"]
            lang_data.append(i)
        temp_data = {"org": org, "data": lang_data}
        res.append(temp_data)

    return Response(res, status=status.HTTP_200_OK)


@swagger_auto_schema(
    method="post",
    manual_parameters=[
        openapi.Parameter(
            "task_id",
            openapi.IN_QUERY,
            description=("An integer to pass the task id"),
            type=openapi.TYPE_INTEGER,
            required=True,
        )
    ],
    responses={200: "Task is reopened"},
)
@api_view(["POST"])
def reopen_translation_voiceover_task(request):
    task_id = request.data["task_id"]

    try:
        task = Task.objects.get(pk=task_id)
    except Task.DoesNotExist:
        return Response({"message": "Task not found"}, status=status.HTTP_404_NOT_FOUND)

    if "REVIEW" in task.task_type:
        translation_completed_obj = (
            Translation.objects.filter(status="TRANSLATION_REVIEW_COMPLETE")
            .filter(target_language=task.target_language)
            .filter(video=task.video)
            .first()
        )
        translation_inprogress_obj = (
            Translation.objects.filter(status="TRANSLATION_REVIEW_INPROGRESS")
            .filter(target_language=task.target_language)
            .filter(video=task.video)
            .first()
        )
        voice_over_obj = (
            VoiceOver.objects.filter(status="VOICEOVER_REVIEW_COMPLETE")
            .filter(video=task.video)
            .filter(target_language=task.target_language)
            .first()
        )
    else:
        translation_review_task = (
            Task.objects.filter(video=task.video)
            .filter(target_language=task.target_language)
            .filter(task_type="TRANSLATION_REVIEW")
            .first()
        )
        if (
            translation_review_task is not None
            and translation_review_task.is_active == True
        ):
            return Response(
                {
                    "message": "Can not reopen this task. Corrosponding Translation Review task is active"
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        translation_completed_obj = (
            Translation.objects.filter(status="TRANSLATION_EDIT_COMPLETE")
            .filter(target_language=task.target_language)
            .filter(video=task.video)
            .first()
        )
        translation_inprogress_obj = (
            Translation.objects.filter(status="TRANSLATION_EDIT_INPROGRESS")
            .filter(target_language=task.target_language)
            .filter(video=task.video)
            .first()
        )
        voice_over_obj = (
            VoiceOver.objects.filter(status="VOICEOVER_EDIT_COMPLETE")
            .filter(video=task.video)
            .filter(target_language=task.target_language)
            .first()
        )
    if (
        translation_inprogress_obj is not None
        and translation_completed_obj is not None
        and voice_over_obj is not None
    ):
        translation_completed_obj.parent = None
        translation_completed_obj.save()
        translation_inprogress_obj.delete()
        translation_completed_obj.status = (
            "TRANSLATION_REVIEW_INPROGRESS"
            if "TRANSLATION_REVIEW" in task.task_type
            else "TRANSLATION_EDIT_INPROGRESS"
        )
        translation_completed_obj.save()

        data = download_json_from_azure_blob(
            app_name,
            voice_over_obj.video.id,
            voice_over_obj.task.id,
            voice_over_obj.target_language,
        )
        voice_over_obj.payload = data
        voice_over_obj.status = "VOICEOVER_EDIT_INPROGRESS"
        voice_over_obj.save()
        task.status = "REOPEN"
        task.save()

        return Response({"message": "Task is reopened."}, status=status.HTTP_200_OK)
    else:
        return Response(
            {"message": "Can not reopen this task."},
            status=status.HTTP_400_BAD_REQUEST,
        )

@api_view(["POST"])
def csv_bulk_regenerate(request):
    """
    API Endpoint to upload a csv file to regenerate failed VOTR tasks
    Endpoint: /voiceover/csv_bulk_regenerate/
    Method: POST
    """

    org_id = request.data.get("org_id")
    csv_content = request.data.get("csv")

    try:
        org = Organization.objects.get(pk=org_id)
    except Organization.DoesNotExist:
        return Response(
            {"message": "Organization not found"}, status=status.HTTP_404_NOT_FOUND
        )

    if not org.organization_owners.filter(id=request.user.id).exists():
        return Response(
            {"message": "You are not allowed to upload CSV."},
            status=status.HTTP_403_FORBIDDEN,
        )

    decrypted = base64.b64decode(csv_content).decode("utf-8")
    task_ids = []
    with io.StringIO(decrypted) as fp:
        reader = csv.reader(fp, delimiter=",", quotechar='"')
        for row in reader:
            if row and row[0].strip():
                task_ids.append(int(row[0]))

    if len(task_ids) > 30:
        return Response(
            {"message": "Number of task id's is greater than 30."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    errors = []

    for task_id in task_ids:
        try:
            task_obj = Task.objects.get(pk=task_id)
            if task_obj.video.project_id.organization_id.id != org_id:
                errors.append(
                    {
                        "row_no": f"Task {task_id}",
                        "message": f"Task Id does not belong to your organization",
                    }
                )
                continue
            # add flower queue check
        except Task.DoesNotExist:
            errors.append(
                {
                    "row_no": f"Task {task_id}",
                    "message": f"Task Id does not exists",
                }
            )
            continue

        voiceover_obj = get_voice_over_id(task_obj)

        if voiceover_obj is None:
            errors.append(
                {
                    "row_no": f"Task {task_id}",
                    "message": f"Voiceover object does not exists",
                }
            )
            continue

        transcription_task = Task.objects.filter(video=task_obj.video, task_type="TRANSCRIPTION_EDIT", status="COMPLETE").first()
        if transcription_task is None:
            errors.append(
                {
                    "row_no": f"Task {task_id}",
                    "message": f"Transcription not completed yet for this VOTR task",
                }
            )
            continue

        transcript = get_transcript_id(transcription_task)
        transcript_obj = Transcript.objects.get(pk=transcript.id)
        translation = Translation.objects.filter(task=task_obj).first()
        translation.transcript = transcript_obj
        translation.save()

    if len(errors) > 0:
        return Response(
            {"message": "Invalid CSV", "response": errors},
            status=status.HTTP_400_BAD_REQUEST,
        )
    else:
        for task_id in task_ids:
            celery_nmt_tts_call.delay(task_id)
        return Response(
            {"message": "CSV uploaded successfully"}, status=status.HTTP_200_OK
        )