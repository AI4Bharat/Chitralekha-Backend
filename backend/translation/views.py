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
from .utils import validate_uuid4

TRANSLATION_API_URL = "http://216.48.181.177:5050"


class TranslationView(APIView):
    permission_classes = (IsAuthenticatedOrReadOnly,)

    def get(self, request):
        # Get the query params
        transcript_id = request.query_params.get('transcript_id')
        target_lang = request.query_params.get('target_lang')
        get_latest = request.query_params.get('get_latest')

        # Ensure that the UUID is valid
        if not validate_uuid4(transcript_id):
            return Response({
                'error': 'Invalid transcript_id.'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Convert get_latest to boolean
        get_latest = get_latest == 'true'

        # Ensure that required params are present
        if not (transcript_id and target_lang):
            return Response({
                'error': 'Missing required query params [transcript_id, target_lang].'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Get the translation for the given transcript_id, target_lang and user_id
        try:
            queryset = Translation.objects.get(
                transcript_id=transcript_id, target_lang=target_lang, user=request.user.id)
        # If no translation exists for this user, check if the latest translation can be fetched
        except Translation.DoesNotExist:
            if get_latest:
                queryset = Translation.objects.filter(
                    transcript_id=transcript_id, target_lang=target_lang
                ).order_by('-updated_at').first()
            else:
                queryset = None

        # If queryset is empty, return appropriate error
        if not queryset:
            return Response({
                'error': 'No translation found for the given transcript_id and target_lang.'
            }, status=status.HTTP_404_NOT_FOUND)

        # Serialize and return the data
        serializer = TranslationSerializer(queryset)
        return Response(serializer.data)
    
    def post(self, request):
        # Get the required data from the POST body
        translation_id = request.data['translation_id']
        target_lang = request.data['target_lang']
        captions = request.data['captions']
        user = request.user

        created = False
        # Try to get the translation for the given translation_id and target_lang
        try:
            translation = Translation.objects.get(
                pk=translation_id, target_lang=target_lang)
            # If the translation mentioned does not belong to the current user,
            # create a new translation with parent as referred translation_id
            if translation.user != user:
                new_translation = Translation.objects.create(
                    translation_type='mc',
                    parent=translation,
                    transcript=translation.transcript,
                    target_lang=target_lang,
                    user=user,
                    payload=captions
                )
                new_translation.save()
                created = True
            # Update the existing translation
            else:
                translation.payload = captions
                translation.translation_type = 'he'
                translation.save()
        # If no translation exists for the given translation_id and target_lang,
        # return error response
        except Translation.DoesNotExist:
            return Response({
                'error': 'No translation found for the given translation_id and target_lang.'
            }, status=status.HTTP_404_NOT_FOUND)

        # Return the appropriate response depending on whether a new translation was created or not
        if created:
            return Response({
                'message': 'Translation created successfully.'
            }, status=status.HTTP_201_CREATED)

        return Response({
            'message': 'Translation updated successfully.'
        }, status=status.HTTP_200_OK)


@api_view(['GET'])
def get_supported_languages(request):
    # Make a request to the Translation API
    response = requests.get(TRANSLATION_API_URL + '/supported_languages/')

    # If the request was successful, return the response data
    if response.status_code == 200:
        return Response(response.json(), status=status.HTTP_200_OK)

    # If the request was not successful, return the error response
    return Response({
        'error': 'Error while fetching supported languages.'
    }, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
def generate_translation(request):
    # Get the query params
    transcript_id = request.query_params.get('transcript_id')
    target_lang = request.query_params.get('target_lang')

    # Ensure that the UUID is valid
    if not validate_uuid4(transcript_id):
        return Response({
            'error': 'Invalid transcript_id.'
        }, status=status.HTTP_400_BAD_REQUEST)

    # Ensure that required params are present
    if not (transcript_id and target_lang):
        return Response({
            'error': 'Missing required query params [transcript_id, target_lang].'
        }, status=status.HTTP_400_BAD_REQUEST)

    # Check if the given transcript ID exists
    transcript = get_object_or_404(Transcript, pk=transcript_id)

    # Check if the cached translation is valid and return if it is valid
    try:
        translation = Translation.objects.get(
            transcript=transcript_id, target_lang=target_lang, user=request.user.id)
        if (translation.updated_at - translation.transcript.updated_at).total_seconds() >= 0:
            serializer = TranslationSerializer(translation)
            return Response(serializer.data)
    # If there is no cached translation, create a new one
    except Translation.DoesNotExist:
        translation = Translation.objects.create(
            translation_type='mg',
            transcript_id=transcript_id,
            target_lang=target_lang,
            user=None,
            payload={}
        )

    # Read the sentences from the transcript
    sentence_list = []
    vtt_output = transcript.payload['output']
    for vtt_line in webvtt.read_buffer(StringIO(vtt_output)):
        sentence_list.append(vtt_line.text)

    # Create the request body and send a GET request to the Translation API
    request_body = {
        "text_lines": sentence_list,
        "source_language": 'en',
        "target_language": target_lang
    }
    response = requests.post(TRANSLATION_API_URL +
                             '/batch_translate/', json=request_body)

    # If the request was successful, load the payload into the Translation object
    # and return the response
    if response.status_code == 200:
        payload = []
        for (source, target) in zip(sentence_list, response.json()['text_lines']):
            payload.append({
                "source": source,
                "target": target
            })
        translation.payload = {
            "translations": payload
        }
        translation.save()

        serializer = TranslationSerializer(translation)
        return Response(serializer.data)

    return Response({
        'error': 'Error while generating translation.',
    }, status=status.HTTP_400_BAD_REQUEST)
