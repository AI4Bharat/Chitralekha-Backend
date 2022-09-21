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

from .metadata import INDIC_TRANS_SUPPORTED_LANGUAGES
from .models import (
    Translation,
    MACHINE_GENERATED,
    MANUALLY_CREATED,
    UPDATED_MACHINE_GENERATED,
)
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
            "load_latest_transcript",
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
def retrieve_translation(request):
    """
    Endpoint to retrive a translation for a given transcript and language
    """

    # Get the query params
    transcript_id = request.query_params.get("transcript_id")
    target_language = request.query_params.get("target_language")
    load_latest_transcript = request.query_params.get("load_latest_transcript", "false")
    translation_type = request.query_params.get("translation_type")

    # Convert load_latest_transcript to boolean
    load_latest_transcript = load_latest_transcript == "true"

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
        if load_latest_transcript:
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


@swagger_auto_schema(
    method="post",
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        required=["target_language", "payload"],
        properties={
            "translation_id": openapi.Schema(
                type=openapi.TYPE_STRING,
                description="An integer identifying the translation instance",
            ),
            "target_language": openapi.Schema(
                type=openapi.TYPE_STRING,
                description="A string to pass the target language of the translation",
            ),
            "payload": openapi.Schema(
                type=openapi.TYPE_STRING,
                description="A string to pass the translated subtitles and metadata",
            ),
            "transcript_id": openapi.Schema(
                type=openapi.TYPE_STRING,
                description="A string to pass the transcript uuid",
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
@permission_classes([IsAuthenticated])
def save_translation(request):

    # Get the required data from the POST body
    translation_id = request.data.get("translation_id", None)
    target_language = request.data["target_language"]
    payload = request.data["payload"]
    user = request.user

    # If translation_id is not present, save a new translation object
    if translation_id is None:

        # Check if transcript_id is present in the POST body
        if "transcript_id" not in request.data:
            return Response(
                {
                    "error": "Transcript_id is missing from the POST body, which needs to be passed if translation_id is not passed."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Get the transcript_id from the POST body
        transcript_id = request.data["transcript_id"]

        try:
            # Get a transcript object for the given transcript_id
            transcript = Transcript.objects.get(id=transcript_id)

        except Transcript.DoesNotExist:
            return Response(
                {"error": "No transcript found for the given transcript_id."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Create a translation object
        new_translation = Translation.objects.create(
            translation_type=MANUALLY_CREATED,
            transcript=transcript,
            target_language=target_language,
            user=user,
            payload=payload,
        )

    else:
        # Try to get the translation for the given translation_id and target_language
        try:
            translation = Translation.objects.get(pk=translation_id)

        except Translation.DoesNotExist:
            return Response(
                {
                    "error": "No translation found for the given translation_id and target_language."
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        # If the translation belongs to the current user, update the translation
        if translation.user == user:
            translation.payload = payload
            translation.save()

            return Response(
                {
                    "message": "Translation updated successfully.",
                    "id": translation.id,
                    "data": translation.payload,
                },
                status=status.HTTP_200_OK,
            )

        # else if the user is not assigned, create a new translation object
        else:

            # Check if the translation doesn't have a user
            if translation.user is not None:
                return Response(
                    {
                        "error": "Translation already has a user assigned to it. You cannot edit this translation."
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Since the translation doesn't have a user, it's of type machine generated
            # so the edited version should be of type updated machine generated
            new_translation = Translation.objects.create(
                translation_type=UPDATED_MACHINE_GENERATED,
                parent=translation,
                transcript=translation.transcript,
                target_language=target_language,
                user=user,
                payload=payload,
            )

    new_translation.save()
    return Response(
        {
            "message": "Translation created successfully.",
            "id": new_translation.id,
            "data": new_translation.payload,
        },
        status=status.HTTP_200_OK,
    )


@api_view(["GET"])
def get_supported_languages(request):

    # Return the allowed translations and model codes
    return Response(
        INDIC_TRANS_SUPPORTED_LANGUAGES,
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
        payload.append({"source": source, "target": target})
    translation.payload = {"translations": payload}
    translation.save()

    # Return the translation
    serializer = TranslationSerializer(translation)
    return Response(serializer.data, status=status.HTTP_200_OK)
