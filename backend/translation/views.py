from io import StringIO

import requests
import webvtt

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticatedOrReadOnly
from rest_framework.response import Response
from rest_framework.views import APIView

from transcript.models import Transcript
from .models import Translation
from .serializers import TranslationSerializer
from .utils import validate_uuid4, get_batch_translations_using_indictrans_nmt_api

TRANSLATION_API_URL = "http://216.48.181.177:5050"


class TranslationView(APIView):
    permission_classes = (IsAuthenticatedOrReadOnly,)

    def get(self, request):
        # Get the query params
        transcript_id = request.query_params.get("transcript_id")
        target_lang = request.query_params.get("target_lang")
        get_latest = request.query_params.get("get_latest")

        # Ensure that the UUID is valid
        if not validate_uuid4(transcript_id):
            return Response(
                {"error": "Invalid transcript_id."}, status=status.HTTP_400_BAD_REQUEST
            )

        # Convert get_latest to boolean
        get_latest = get_latest == "true"

        # Ensure that required params are present
        if not (transcript_id and target_lang):
            return Response(
                {
                    "error": "Missing required query params [transcript_id, target_lang]."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Get the translation for the given transcript_id, target_lang and user_id
        queryset = (
            Translation.objects.filter(
                transcript_id=transcript_id,
                target_lang=target_lang,
                user=request.user.id,
            )
            .order_by("-updated_at")
            .first()
        )
        # If no translation exists for this user, check if the latest translation can be fetched
        if queryset is None:
            if get_latest:
                queryset = (
                    Translation.objects.filter(
                        transcript_id=transcript_id, target_lang=target_lang
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
                    "error": "No translation found for the given transcript_id and target_lang."
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        # Serialize and return the data
        serializer = TranslationSerializer(queryset)
        return Response(serializer.data)

    def post(self, request):
        # Get the required data from the POST body
        translation_id = request.data["translation_id"]
        target_lang = request.data["target_lang"]
        captions = request.data["captions"]
        user = request.user

        created = False
        # Try to get the translation for the given translation_id and target_lang
        try:
            translation = Translation.objects.get(
                pk=translation_id, target_lang=target_lang
            )
            # If the translation mentioned does not belong to the current user,
            # create a new translation with parent as referred translation_id
            if translation.user != user:
                new_translation = Translation.objects.create(
                    translation_type="mc",
                    parent=translation,
                    transcript=translation.transcript,
                    target_lang=target_lang,
                    user=user,
                    payload=captions,
                )
                new_translation.save()
                created = True
            # Update the existing translation
            else:
                translation.payload = captions
                translation.translation_type = "he"
                translation.save()
        # If no translation exists for the given translation_id and target_lang,
        # return error response
        except Translation.DoesNotExist:
            return Response(
                {
                    "error": "No translation found for the given translation_id and target_lang."
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        # Return the appropriate response depending on whether a new translation was created or not
        if created:
            return Response(
                {"message": "Translation created successfully."},
                status=status.HTTP_201_CREATED,
            )

        return Response(
            {"message": "Translation updated successfully."}, status=status.HTTP_200_OK
        )


@api_view(["GET"])
def get_supported_languages(request):
    # Make a request to the Translation API
    response = requests.get(TRANSLATION_API_URL + "/supported_languages/")

    # If the request was successful, return the response data
    if response.status_code == 200:
        return Response(response.json(), status=status.HTTP_200_OK)

    # If the request was not successful, return the error response
    return Response(
        {"error": "Error while fetching supported languages."},
        status=status.HTTP_400_BAD_REQUEST,
    )


@api_view(["GET"])
def generate_translation(request):
    """GET Request endpoint to generate translation for a given transcript_id and target_lang

    Args:
        request : HTTP GET request

    GET params:
        transcript_id : UUID of the transcript
        target_lang : Target language of the translation
        batch_size : Number of transcripts to be translated at a time [optional]

    Returns:
        Response: Response containing the generated translations
    """

    # Get the query params
    transcript_id = request.query_params.get("transcript_id")
    target_lang = request.query_params.get("target_lang")
    batch_size = request.query_params.get("batch_size", 75)

    # Ensure that the UUID is valid
    if not validate_uuid4(transcript_id):
        return Response(
            {"error": "Invalid transcript_id."}, status=status.HTTP_400_BAD_REQUEST
        )

    # Ensure that required params are present
    if not (transcript_id and target_lang):
        return Response(
            {"error": "Missing required query params [transcript_id, target_lang]."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Check if the given transcript ID exists
    transcript = get_object_or_404(Transcript, pk=transcript_id)

    # Get the transcript source language
    source_lang = transcript.language

    # Check if the cached translation is valid and return if it is valid
    translation = (
        Translation.objects.filter(
            transcript=transcript_id, target_lang=target_lang, user=request.user.id
        )
        .order_by("-updated_at")
        .first()
    )
    if translation is not None:
        if (
            translation.updated_at - translation.transcript.updated_at
        ).total_seconds() >= 0:
            serializer = TranslationSerializer(translation)
            return Response(serializer.data)

    # If there is no cached translation, create a new one
    translation = Translation.objects.create(
        translation_type="mg",
        transcript_id=transcript_id,
        target_lang=target_lang,
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
            target_language=target_lang,
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
    return Response(serializer.data)
