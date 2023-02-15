from io import StringIO
import base64
import json
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
from scipy.io.wavfile import write
import os
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from transcript.models import Transcript
from video.models import Video
from task.models import Task
from rest_framework.decorators import action
from django.http import HttpResponse
from django.core.files.base import ContentFile
import requests
from translation.metadata import INDIC_TRANS_SUPPORTED_LANGUAGES
from .models import (
    VoiceOver,
    MACHINE_GENERATED,
    MANUALLY_CREATED,
    VOICEOVER_TYPE_CHOICES,
    VOICEOVER_SELECT_SOURCE,
    VOICEOVER_EDITOR_ASSIGNED,
    VOICEOVER_EDIT_INPROGRESS,
    VOICEOVER_EDIT_COMPLETE,
    VOICEOVER_REVIEWER_ASSIGNED,
    VOICEOVER_REVIEW_INPROGRESS,
    VOICEOVER_REVIEW_COMPLETE,
)
from datetime import datetime, date, timedelta
from .decorators import is_voice_over_editor
from .serializers import VoiceOverSerializer
from .utils import uploadToBlobStorage, generate_voiceover_payload, get_tts_output
from config import voice_over_payload_offset_size


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
        if task.status == "COMPLETE":
            voice_over_id = (
                voice_over.filter(video=task.video)
                .filter(status="VOICEOVER_EDIT_COMPLETE")
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
    if voice_over.translation:
        payload_offset_size = voice_over_payload_offset_size - 1
        count_cards = (
            len(voice_over.translation.payload["payload"])
            - voice_over_payload_offset_size
            + 1
        )
        first_offset = voice_over_payload_offset_size // 2 + 1
        start_offset = (
            first_offset + current_offset - 1 * payload_offset_size // 2
        ) - (payload_offset_size // 2)
        end_offset = (first_offset + current_offset - 1 * payload_offset_size // 2) + (
            payload_offset_size // 2
        )

        generate_voice_over = True
        if end_offset >= len(voice_over.translation.payload["payload"]) - 2:
            next = None
            previous = offset - 1
        elif offset == 1:
            previous = None
            next = offset + 1
        else:
            next = offset + 1
            previous = offset - 1
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
        for text, index in translation_payload:
            audio_index = str(start_offset + index)

            if (
                voice_over.payload
                and "payload" in voice_over.payload
                and len(voice_over.payload["payload"].keys()) > 0
                and audio_index in voice_over.payload["payload"].keys()
                and "audioContent"
                in voice_over.payload["payload"][audio_index]["audio"]
            ):
                input_sentences.append(
                    (
                        voice_over.payload["payload"][audio_index]["text"],
                        voice_over.payload["payload"][audio_index]["audio"],
                        False,
                    )
                )
            else:
                input_sentences.append((text["target_text"], "", True))

        voiceover_machine_generated = generate_voiceover_payload(
            input_sentences, task.target_language
        )

        for i in range(len(voiceover_machine_generated)):
            start_time = translation_payload[i][0]["start_time"]
            end_time = translation_payload[i][0]["end_time"]
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
            ) * 1000
            sentences_list.append(
                {
                    "time_difference": t_d,
                    "start_time": translation_payload[i][0]["start_time"],
                    "end_time": translation_payload[i][0]["end_time"],
                    "text": voiceover_machine_generated[i][0],
                    "audio": voiceover_machine_generated[i][1],
                }
            )
        payload = sentences_list
        payload = {"payload": sentences_list}
    elif voice_over.voice_over_type == "MANUALLY_CREATED":
        if voice_over.payload and voice_over.payload["payload"]:
            count = 0
            for i in range(start_offset, end_offset + 1):
                if str(i) in voice_over.payload["payload"]:
                    sentences_list.append(voice_over.payload["payload"][str(i)])
                else:
                    start_time = translation_payload[count][0]["start_time"]
                    end_time = translation_payload[count][0]["end_time"]
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
                    ) * 1000
                    sentences_list.append(
                        {
                            "time_difference": t_d,
                            "start_time": translation_payload[count][0]["start_time"],
                            "end_time": translation_payload[count][0]["end_time"],
                            "text": translation_payload[count][0]["target_text"],
                            "audio": "",
                        }
                    )
                    count += 1
        payload = {"payload": sentences_list}
    else:
        return Response(
            {"message": "Payload not generated for voice over"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    return Response(
        {
            "count": count_cards,
            "next": next,
            "current": offset,
            "previous": previous,
            "payload": payload,
            "source_type": voice_over.voice_over_type,
        },
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

    voice_over = get_voice_over_id(task)
    if voice_over is not None:
        voice_over_id = voice_over.id
    else:
        return Response(
            {"message": "VoiceOver doesn't exist."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    try:
        voice_over = VoiceOver.objects.get(pk=voice_over_id)
        target_language = voice_over.target_language
        translation = voice_over.translation

        # Check if the transcript has a user
        if task.user != request.user:
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

            payload_offset_size = voice_over_payload_offset_size - 1
            count = (
                len(voice_over.translation.payload["payload"])
                - voice_over_payload_offset_size
            )
            first_offset = voice_over_payload_offset_size // 2 + 1
            current_offset = offset - 1
            start_offset = (
                first_offset + current_offset - 1 * payload_offset_size // 2
            ) - (payload_offset_size // 2)
            end_offset = (
                first_offset + current_offset - 1 * payload_offset_size // 2
            ) + (payload_offset_size // 2)

            if "EDIT" in task.task_type:
                if request.data.get("final"):
                    if (
                        VoiceOver.objects.filter(status=VOICEOVER_EDIT_COMPLETE)
                        .filter(target_language=target_language)
                        .filter(translation=translation)
                        .first()
                        is not None
                    ):
                        return Response(
                            {"error": "Voice Over Edit already exists."},
                            status=status.HTTP_201_CREATED,
                        )
                    else:
                        audios = []
                        audio_name = task.video.name + "_" + task.target_language
                        file_path = os.path.join(
                            "./temporary_audio_files_dir/" + audio_name + ".json"
                        )
                        try:
                            for audio in payload["payload"]:
                                audios.append(
                                    {
                                        "start_time": audio["start_time"],
                                        "end_time": audio["end_time"],
                                        "audio": audio["audio"],
                                    }
                                )
                                """
                                if len(audio["audio"]) > 0:
                                    decode_string = base64.b64decode(audio["audio"]["audio"][0]["audioContent"])
                                    sample_rate = audio["audio"]["config"]["samplingRate"]
                                    wav_file.write(decode_string)
                                """
                            with open(file_path, "w") as outfile:
                                json.dump(audios, outfile)
                            # uploadToBlobStorage(file_path)
                        except:
                            return Response(
                                {
                                    "error": "Voice Over can't be completed as audio file couldn't be processed."
                                },
                                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            )
                        ts_status = VOICEOVER_EDIT_COMPLETE
                        voice_over_type = voice_over.voice_over_type
                        voice_over_obj = VoiceOver.objects.create(
                            voice_over_type=voice_over_type,
                            parent=voice_over,
                            translation=voice_over.translation,
                            video=voice_over.video,
                            target_language=voice_over.target_language,
                            user=user,
                            payload={"audio": audios},
                            status=ts_status,
                            task=task,
                        )
                        task.status = "COMPLETE"
                        task.save()
                        change_active_status_of_next_tasks(
                            task, target_language, voice_over_obj
                        )
                else:
                    translation_payload = []
                    for index, voice_over_payload in enumerate(payload["payload"]):
                        if (
                            voice_over.voice_over_type == "MACHINE_GENERATED"
                            and "text_changed" in voice_over_payload
                            and voice_over_payload["text_changed"] == True
                        ):
                            translation_payload.append(
                                (voice_over_payload["text"], "", True)
                            )
                        else:
                            translation_payload.append(
                                (
                                    voice_over_payload["text"],
                                    voice_over_payload["audio"],
                                    False,
                                )
                            )
                    voiceover_machine_generated = generate_voiceover_payload(
                        translation_payload, task.target_language
                    )

                    voice_over_obj = (
                        VoiceOver.objects.filter(status=VOICEOVER_EDIT_INPROGRESS)
                        .filter(target_language=target_language)
                        .filter(translation=translation)
                        .first()
                    )
                    ts_status = VOICEOVER_EDIT_INPROGRESS
                    voice_over_type = voice_over.voice_over_type
                    if voice_over_obj is not None:
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
                            ) * 1000
                            voice_over_obj.payload["payload"][start_offset + i] = {
                                "time_difference": t_d,
                                "start_time": payload["payload"][i]["start_time"],
                                "end_time": payload["payload"][i]["end_time"],
                                "text": payload["payload"][i]["text"],
                                "audio": voiceover_machine_generated[i][1],
                            }
                        # voice_over_obj.payload[start_offset : end_offset] = voiceover_payload
                        voice_over_obj.voice_over_type = voice_over_type
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
                                {"error": "VoiceOver object does not exist."},
                                status=status.HTTP_404_NOT_FOUND,
                            )
                        voice_over_obj = VoiceOver.objects.create(
                            voice_over_type=voice_over_type,
                            parent=voice_over_obj,
                            translation=voice_over_obj.translation,
                            video=voice_over_obj.video,
                            target_language=voice_over_obj.target_language,
                            user=user,
                            payload={"payload": {}},
                            status=ts_status,
                            task=task,
                        )
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
                            ) * 1000

                            voice_over_obj.payload["payload"][start_offset + i] = {
                                "time_difference": t_d,
                                "start_time": payload["payload"][i]["start_time"],
                                "end_time": payload["payload"][i]["end_time"],
                                "text": payload["payload"][i]["text"],
                                "audio": voiceover_machine_generated[i][1],
                            }
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
                            {"error": "Reviewed Voice Over already exists."},
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
                        "task_id": task.id,
                        "voice_over_id": voice_over_obj.id,
                        "data": voice_over_obj.payload,
                    },
                    status=status.HTTP_200_OK,
                )
    except VoiceOver.DoesNotExist:
        return Response(
            {"message": "VoiceOver doesn't exist."},
            status=status.HTTP_400_BAD_REQUEST,
        )


@api_view(["GET"])
def get_supported_languages(request):

    # Return the allowed voice_overs and model codes
    return Response(
        [
            {"label": label, "value": value}
            for label, value in INDIC_TRANS_SUPPORTED_LANGUAGES.items()
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
