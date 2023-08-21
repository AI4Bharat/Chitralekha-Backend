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
from .metadata import VOICEOVER_SUPPORTED_LANGUAGES, VOICEOVER_LANGUAGE_CHOICES
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
from config import voice_over_payload_offset_size
from .tasks import celery_integration, export_voiceover_async
from django.db.models import Count, F, Sum
from operator import itemgetter
from itertools import groupby
from pydub import AudioSegment


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
            voice_over_id = None
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

    if (
        voice_over.payload
        and "payload" in voice_over.payload
        and "audio_not_generated" in voice_over.payload
        and len(voice_over.payload["audio_not_generated"]) > 0
    ):
        return Response(
            {
                "data": voice_over.payload["audio_not_generated"],
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
        payload_offset_size = voice_over_payload_offset_size - 1
        if voice_over.voice_over_type == "MACHINE_GENERATED":
            count_cards = (
                len(list(voice_over.payload["payload"].keys()))
                - voice_over_payload_offset_size
                + 1
            )
            count_cards += 1
        else:
            """
            count_cards = (
                len(voice_over.translation.payload["payload"])
                - voice_over_payload_offset_size
                + 1
            )
            """
            count_cards = len(voice_over.translation.payload["payload"]) - 1
        first_offset = voice_over_payload_offset_size // 2 + 1
        start_offset = (
            first_offset + current_offset - 1 * payload_offset_size // 2
        ) - (payload_offset_size // 2)
        end_offset = (first_offset + current_offset - 1 * payload_offset_size // 2) + (
            payload_offset_size // 2
        )

        generate_voice_over = True
        if end_offset > count_cards:
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
            start_time = translation_payload[index][0]["start_time"]
            end_time = translation_payload[index][0]["end_time"]
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
            sentences_list.append(
                {
                    "id": str(int(audio_index) + 1),
                    "time_difference": t_d,
                    "start_time": start_time,
                    "end_time": end_time,
                    "text": voice_over.payload["payload"][str(audio_index)]["text"],
                    "audio": voice_over.payload["payload"][str(audio_index)]["audio"],
                    "audio_speed": 1,
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
                "count": count_cards,
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
            "completed_count": count_cards,
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
            if task.status == "POST_PROCESS":
                return Response(
                    {"message": "Voice Over is in Post Process stage."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            payload_offset_size = voice_over_payload_offset_size - 1
            if voice_over.voice_over_type == "MACHINE_GENERATED":
                count_cards = (
                    len(list(voice_over.payload["payload"].keys()))
                    - voice_over_payload_offset_size
                    + 1
                )
                count_cards += 1
            else:
                """
                count_cards = (
                    len(voice_over.translation.payload["payload"])
                    - voice_over_payload_offset_size
                    + 1
                )
                """
                count_cards = len(voice_over.translation.payload["payload"]) - 1
            first_offset = voice_over_payload_offset_size // 2 + 1
            current_offset = offset - 1
            start_offset = (
                first_offset + current_offset - 1 * payload_offset_size // 2
            ) - (payload_offset_size // 2)
            end_offset = (
                first_offset + current_offset - 1 * payload_offset_size // 2
            ) + (payload_offset_size // 2)

            if end_offset > count_cards:
                next = None
                previous = offset - 1
            elif offset == 1:
                previous = None
                next = offset + 1
            else:
                next = offset + 1
                previous = offset - 1

            sentences_list = []
            if "EDIT" in task.task_type:
                translation_payload = []
                for index, voice_over_payload in enumerate(payload["payload"]):
                    start_time = voice_over_payload["start_time"]
                    end_time = voice_over_payload["end_time"]
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
                    voiceover_machine_generated = generate_voiceover_payload(
                        translation_payload, task.target_language, task
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
                        file_name = "Chitralekha_Video_{}_{}_{}".format(
                            voice_over_obj.video.id,
                            time_now,
                            voice_over_obj.target_language,
                        )
                        file_path = "temporary_video_audio_storage"
                        task.status = "POST_PROCESS"
                        task.save()
                        logging.info("Calling Async Celery Integration")
                        celery_integration.delay(
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
                        "completed_count": completed_count,
                        "count": count_cards,
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
    ],
    responses={200: "VO is exported"},
)
@api_view(["GET"])
def export_voiceover(request):
    task_id = request.query_params.get("task_id")
    export_type = request.query_params.get("export_type")
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
        elif export_type == "flac":
            return Response(
                {
                    "azure_url": voice_over.azure_url_audio,
                },
                status=status.HTTP_200_OK,
            )
        elif export_type == "mp3":
            logging.info(
                "Downloading audio from Azure Blob %s", voice_over.azure_url_audio
            )
            export_voiceover_async.delay(
                voice_over.task.id, export_type, request.user.id
            )
            return Response(
                {
                    "message": "Please wait. The audio link will be emailed to you.",
                },
                status=status.HTTP_200_OK,
            )
        elif export_type == "wav":
            export_voiceover_async.delay(
                voice_over.task.id, export_type, request.user.id
            )
            return Response(
                {
                    "message": "Please wait. The audio link will be emailed to you.",
                },
                status=status.HTTP_200_OK,
            )
    else:
        return Response(
            {"message": "The supported formats are : {mp4, mp3, flac, wav} "},
            status=status.HTTP_404_NOT_FOUND,
        )


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
