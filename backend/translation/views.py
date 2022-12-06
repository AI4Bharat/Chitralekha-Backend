from io import StringIO

import webvtt
from django.shortcuts import get_object_or_404
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from transcript.models import Transcript
from video.models import Video
from task.models import Task
from rest_framework.decorators import action

from .metadata import INDIC_TRANS_SUPPORTED_LANGUAGES
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

from .decorators import is_translation_editor
from .serializers import TranslationSerializer
from .utils import get_batch_translations_using_indictrans_nmt_api


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
            "translation_type",
            openapi.IN_QUERY,
            description=("A string to pass the target language of the translation"),
            type=openapi.TYPE_STRING,
            required=True,
        ),
        openapi.Parameter(
            "load_latest_translation",
            openapi.IN_QUERY,
            description=(
                "A string to pass whether to get the latest translation or not"
            ),
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
def retrieve_translation(request):
    """
    Endpoint to retrive a translation for a given transcript and language
    """

    # Get the query params
    transcript_id = request.query_params.get("transcript_id")
    target_language = request.query_params.get("target_language")
    load_latest_translation = request.query_params.get(
        "load_latest_translation", "false"
    )
    translation_type = request.query_params.get("translation_type")

    # Convert load_latest_translation to boolean
    load_latest_translation = load_latest_translation == "true"

    # Ensure that required params are present
    if not (transcript_id and target_language and translation_type):
        return Response(
            {
                "error": "Missing required query params [transcript_id, target_language, translation_type]."
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Get the translation for the given transcript_id, target_language and user_id
    queryset = (
        Translation.objects.filter(
            transcript_id=transcript_id,
            target_language=target_language,
            user=request.user.id,
            translation_type=translation_type,
        )
        .order_by("-updated_at")
        .first()
    )
    # If no translation exists for this user, check if the latest translation can be fetched
    if queryset is None:
        if load_latest_translation:
            queryset = (
                Translation.objects.filter(
                    transcript_id=transcript_id,
                    target_language=target_language,
                    translation_type=translation_type,
                )
                .order_by("-updated_at")
                .first()
            )
        else:
            queryset = None

    # If queryset is empty, return appropriate error
    if not queryset:
        return Response(
            {
                "error": "No translation found for the given transcript_id, target_language and transcript_type."
            },
            status=status.HTTP_404_NOT_FOUND,
        )

    # Serialize and return the data
    serializer = TranslationSerializer(queryset)
    return Response(serializer.data, status=status.HTTP_200_OK)


def get_translation_id(task):
    translation = Translation.objects.filter(task=task)
    if "EDIT" in task.task_type:
        if task.status == "NEW":
            translation_id = -1
        if task.status == "SELECTED_SOURCE":
            translation_id = (
                translation.filter(video=task.video)
                .filter(target_language=task.target_language)
                .filter(status="TRANSLATION_SELECT_SOURCE")
                .first()
                .id
            )
        if task.status == "INPROGRESS":
            translation_id = (
                translation.filter(video=task.video)
                .filter(target_language=task.target_language)
                .filter(status="TRANSLATION_EDIT_INPROGRESS")
                .first()
                .id
            )
        if task.status == "COMPLETE":
            translation_id = (
                translation.filter(video=task.video)
                .filter(target_language=task.target_language)
                .filter(status="TRANSLATION_EDIT_COMPLETE")
                .first()
                .id
            )
    else:
        if task.status == "NEW":
            translation_id = (
                translation.filter(video=task.video)
                .filter(target_language=task.target_language)
                .filter(status="TRANSLATION_REVIEWER_ASSIGNED")
                .first()
                .id
            )
        if task.status == "INPROGRESS":
            translation_id = (
                translation.filter(video=task.video)
                .filter(target_language=task.target_language)
                .filter(status="TRANSLATION_REVIEW_INPROGRESS")
                .first()
                .id
            )
        if task.status == "COMPLETE":
            translation_id = (
                translation.filter(video=task.video)
                .filter(target_language=task.target_language)
                .filter(status="TRANSLATION_REVIEW_COMPLETE")
                .first()
                .id
            )
    return translation_id


@swagger_auto_schema(
    method="post",
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        required=["task_id", "payload"],
        properties={
            "task_id": openapi.Schema(
                type=openapi.TYPE_STRING,
                description="An integer identifying the translation instance",
            ),
            "payload": openapi.Schema(
                type=openapi.TYPE_STRING,
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

    translation_id = get_translation_id(task)
    try:
        translation = Translation.objects.get(pk=translation_id)
        target_language = translation.target_language
        transcript = translation.transcript

        # Check if the transcript has a user
        if translation.user != request.user:
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

            if translation.translation_type == MACHINE_GENERATED:
                updated_translation_type = UPDATED_MACHINE_GENERATED
            else:
                updated_translation_type = UPDATED_MANUALLY_CREATED

            if "EDIT" in task.task_type:
                if request.data.get("final"):
                    if (
                        Translation.objects.filter(status=TRANSLATION_EDIT_COMPLETE)
                        .filter(target_language=target_language)
                        .filter(transcript=transcript)
                        .first()
                        is not None
                    ):
                        return Response(
                            {"error": "Edit Translation already exists."},
                            status=status.HTTP_201_CREATED,
                        )
                    else:
                        ts_status = TRANSLATION_EDIT_COMPLETE
                        task.status = "COMPLETE"
                        task.save()
                        translation_type = updated_translation_type
                        translation_obj = Translation.objects.create(
                            translation_type=translation_type,
                            parent=translation,
                            transcript=translation.transcript,
                            video=translation.video,
                            target_language=translation.target_language,
                            user=user,
                            payload=payload,
                            status=ts_status,
                            task=task,
                        )

                else:
                    translation_obj = (
                        Translation.objects.filter(status=TRANSLATION_EDIT_INPROGRESS)
                        .filter(target_language=target_language)
                        .filter(transcript=transcript)
                        .first()
                    )
                    ts_status = TRANSLATION_EDIT_INPROGRESS
                    translation_type = translation.translation_type
                    if translation_obj is not None:
                        translation_obj.payload = payload
                        translation_obj.translation_type = translation_type
                        translation_obj.save()
                    else:
                        translation_obj = (
                            Translation.objects.filter(status=TRANSLATION_SELECT_SOURCE)
                            .filter(target_language=target_language)
                            .filter(transcript=transcript)
                            .first()
                        )
                        if translation_obj is None:
                            return Response(
                                {"error": "Translation object does not exist."},
                                status=status.HTTP_404_NOT_FOUND,
                            )
                        translation_obj = Translation.objects.create(
                            translation_type=translation_type,
                            parent=translation_obj,
                            transcript=translation_obj.transcript,
                            video=translation_obj.video,
                            target_language=translation_obj.target_language,
                            user=user,
                            payload=payload,
                            status=ts_status,
                            task=task,
                        )
                        task.status = "INPROGRESS"
                        task.save()
            else:
                if request.data.get("final"):
                    if (
                        Translation.objects.filter(status=TRANSLATION_REVIEW_COMPLETE)
                        .filter(target_language=target_language)
                        .filter(transcript=transcript)
                        .first()
                        is not None
                    ):
                        return Response(
                            {"error": "Reviewed Translation already exists."},
                            status=status.HTTP_201_CREATED,
                        )
                    ts_status = TRANSLATION_REVIEW_COMPLETE
                    translation_type = updated_translation_type
                    translation_obj = Translation.objects.create(
                        translation_type=translation_type,
                        parent=translation_obj,
                        transcript=translation_obj.transcript,
                        video=translation_obj.video,
                        target_language=translation_obj.target_language,
                        user=user,
                        payload=payload,
                        status=ts_status,
                        task=task,
                    )
                    task.status = "COMPLETE"
                    task.save()

                else:
                    translation_obj = (
                        Translation.objects.filter(status=TRANSLATION_REVIEW_INPROGRESS)
                        .filter(target_language=target_language)
                        .filter(transcript=transcript)
                        .first()
                    )
                    ts_status = TRANSLATION_REVIEW_INPROGRESS
                    translation_type = translation.translation_type
                    if translation_obj is not None:
                        translation_obj.payload = payload
                        translation_obj.translation_type = translation_type
                        translation_obj.save()
                        task.status = "INPROGRESS"
                        task.save()
                    else:
                        ts_status = TRANSLATION_REVIEW_INPROGRESS
                        translation_type = updated_translation_type
                        translation_obj = Translation.objects.create(
                            translation_type=translation_type,
                            parent=translation_obj,
                            transcript=translation_obj.transcript,
                            video=translation_obj.video,
                            target_language=translations_obj.target_language,
                            user=user,
                            payload=payload,
                            status=ts_status,
                            task=task,
                        )
                        task.status = "INPROGRESS"
                        task.save()

            return Response(
                {
                    "message": "Translation updated successfully.",
                    "task_id": task.id,
                    "translation_id": translation_obj.id,
                    "data": translation_obj.payload,
                },
                status=status.HTTP_200_OK,
            )
    except Translation.DoesNotExist:
        return Response(
            {"message": "Translation doesn't exist."},
            status=status.HTTP_400_BAD_REQUEST,
        )


@api_view(["GET"])
def get_supported_languages(request):

    # Return the allowed translations and model codes
    return Response(
        [
            {"label": label, "value": value}
            for label, value in INDIC_TRANS_SUPPORTED_LANGUAGES.items()
        ],
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
                "error": "Missing required query params [transcript_id, target_language]."
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
                {"error": translations_output}, status=status.HTTP_400_BAD_REQUEST
            )
        else:
            # Add the translated sentences to the list
            all_translated_sentences.extend(translations_output)

    # Check if the length of the translated sentences is equal to the length of the input sentences
    if len(all_translated_sentences) != len(sentence_list):
        return Response(
            {"error": "Error while generating translation."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Update the translation payload with the generated translations
    payload = []
    for (source, target) in zip(sentence_list, all_translated_sentences):
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
