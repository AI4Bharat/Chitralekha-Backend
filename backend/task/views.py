from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet
from video.models import Video
from project.decorators import is_project_owner
from transcript.views import generate_transcription
from rest_framework.decorators import action
from users.models import User
from transcript.utils.asr import get_asr_supported_languages, make_asr_api_call
from transcript.models import Transcript
from translation.models import Translation
from video.utils import get_subtitles_from_google_video
from rest_framework.permissions import IsAuthenticated
import webvtt
from io import StringIO
import json, sys

from .models import (
    TASK_TYPE,
    Task,
    TRANSCRIPTION_EDIT,
    TRANSCRIPTION_REVIEW,
    TRANSLATION_EDIT,
    TRANSLATION_REVIEW,
    NEW,
    INPROGRESS,
    COMPLETE,
    PRIORITY,
)

from .serializers import TaskSerializer
from users.models import User
from rest_framework.response import Response
from functools import wraps
from rest_framework import status


class TaskViewSet(ModelViewSet):
    """
    API ViewSet for the Video model.
    Performs CRUD operations on the Video model.
    Endpoint: /video/api/
    Methods: GET, POST, PUT, DELETE
    """

    queryset = Task.objects.all()
    serializer_class = TaskSerializer
    permission_classes = (IsAuthenticated,)

    def has_transcript_edit_permission(self, user, video):
        if user in video.project_id.members.all() and (
            user.role == User.TRANSCRIPT_EDITOR
            or user.role == User.UNIVERSAL_EDITOR
            or user.role == User.TRANSCRIPT_REVIEWER
            or user.role == User.PROJECT_MANGAGER
            or user.role == User.ORG_OWNER
            or user.is_superuser
        ):
            return True
        return False

    def has_transcript_review_permission(self, user, video):
        if user in video.project_id.members.all() and (
            user.role == User.UNIVERSAL_EDITOR
            or user.role == User.TRANSCRIPT_REVIEWER
            or user.role == User.PROJECT_MANGAGER
            or user.role == User.ORG_OWNER
            or user.is_superuser
        ):
            return True
        return False

    def has_translate_edit_permission(self, user, video):
        if user in video.project_id.members.all() and (
            user.role == User.UNIVERSAL_EDITOR
            or user.role == User.TRANSLATION_EDITOR
            or user.role == User.TRANSLATION_REVIEWER
            or user.role == User.PROJECT_MANGAGER
            or user.role == User.ORG_OWNER
            or user.is_superuser
        ):
            return True
        return False

    def has_translate_review_permission(self, user, video):
        if user in video.project_id.members.all() and (
            user.role == User.UNIVERSAL_EDITOR
            or user.role == User.TRANSLATION_REVIEWER
            or user.role == User.PROJECT_MANGAGER
            or user.role == User.ORG_OWNER
            or user.is_superuser
        ):
            return True
        return False

    def generate_translation(
        self, video, lang, transcript, user, translation_type, task, payload
    ):
        status = "TRANSLATION_SELECT_SOURCE"
        translate_obj = Translation(
            video=video,
            user=user,
            transcript=transcript,
            payload=payload,
            target_language=lang,
            task=task,
            translation_type=translation_type,
            status=status,
        )
        translate_obj.save()
        return {
            "translate_id": translate_obj.id,
            "data": translate_obj.payload,
            "task_id": task.id,
        }

    def check_duplicate_task(self, task_type, task, user, video):
        if task.filter(task_type=task_type).first() is not None:
            return {
                "message": "Task is already created.",
                "status": status.HTTP_400_BAD_REQUEST,
            }

        if "REVIEW" in task_type:
            edit_task_type = task_type.split("_")[0] + "_" + "EDIT"
            if (
                task.filter(task_type=edit_task_type).filter(status="COMPLETE").first()
                is None
            ):
                return {
                    "message": "Creation of Review task is not permissible until Editing is not completed.",
                    "status": status.HTTP_400_BAD_REQUEST,
                }
            if task.filter(task_type=task_type).filter(user=user).first():
                if not (request.user.role > 4 or request.user.is_superuser):
                    return {
                        "message": "Same user can't be Editor and Reviewer of a video.",
                        "status": status.HTTP_400_BAD_REQUEST,
                    }

        if "TRANSLATION" in task_type:
            if (
                Task.objects.filter(video=video)
                .filter(task_type="TRANSCRIPTION_EDIT")
                .filter(status="COMPLETE")
                .first()
                is None
            ):
                return {
                    "message": "Creation of Translation task is not permissible until Transcription is not done.",
                    "status": status.HTTP_400_BAD_REQUEST,
                }
        return {}

    def check_transcript_exists(self, video, verified_transcript):
        transcript = Transcript.objects.filter(video=video)

        if not verified_transcript:
            if transcript.filter(status="TRANSCRIPTION_EDIT_COMPLETE").first() is None:
                return {
                    "message": "Transcript doesn't exist for this video.",
                    "status": status.HTTP_400_BAD_REQUEST,
                }
            else:
                return transcript.filter(status="TRANSCRIPTION_EDIT_COMPLETE").first()
        else:
            if (
                transcript.filter(status="TRANSCRIPTION_REVIEW_COMPLETE").first()
                is None
            ):
                return {
                    "message": "Reviewed Transcript doesn't exist for this video.",
                    "status": status.HTTP_400_BAD_REQUEST,
                }
            else:
                return transcript.filter(status="TRANSCRIPTION_REVIEW_COMPLETE").first()

    def create_translation_task(
        self,
        video,
        user,
        target_language,
        task_type,
        request,
        verified_transcript,
        eta,
        priority,
        description,
    ):
        task = Task.objects.filter(video=video).filter(target_language=target_language)

        response = self.check_duplicate_task(task_type, task, user, video)
        if len(response) > 0:
            return Response({"message": response["message"]}, status=response["status"])

        response_transcript = self.check_transcript_exists(video, verified_transcript)
        if type(response_transcript) == dict:
            return Response(
                {"message": response_transcript["message"]},
                status=response_transcript["status"],
            )
        else:
            transcript_obj = response_transcript
        if "EDIT" in task_type:
            permitted = self.has_translate_edit_permission(user, video)
        else:
            permitted = self.has_translate_review_permission(user, video)

        if permitted:
            if "EDIT" in task_type:
                translation = (
                    Translation.objects.filter(video=video)
                    .filter(target_language=target_language)
                    .filter(status="TRANSLATION_SELECT_SOURCE")
                    .first()
                )

                if translation is None:
                    new_task = Task(
                        task_type=task_type,
                        video=video,
                        created_by=request.user,
                        user=user,
                        target_language=target_language,
                        status="NEW",
                        eta=eta,
                        description=description,
                        priority=priority,
                        verified_transcript=verified_transcript,
                    )
                    new_task.save()
                    response = {"task_id": new_task.id}
            else:
                edit_task_type = task_type.split("_")[0] + "_" + "EDIT"
                translation = (
                    Translation.objects.filter(video=video)
                    .filter(target_language=target_language)
                    .filter(status="TRANSLATION_EDIT_COMPLETE")
                    .first()
                )
                if translation is None:
                    return Response(
                        {
                            "message": "Translation review task can't be created, as editing is not done yet."
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                else:
                    new_task = Task(
                        task_type=task_type,
                        video=video,
                        created_by=request.user,
                        user=user,
                        target_language=target_language,
                        status="NEW",
                        eta=eta,
                        description=description,
                        priority=priority,
                        # verified_transcript=verified_transcript,
                    )
                    new_task.save()

                    translate_obj = Translation(
                        video=video,
                        user=user,
                        transcript=transcript_obj,
                        parent=translation,
                        payload=translation.payload,
                        target_language=lang,
                        task=new_task,
                        translation_type=translation.translation_type,
                        status="TRANSLATION_REVIEWER_ASSIGNED",
                    )
                    translation_obj.save()
                    response = {
                        "task_id": new_task.id,
                        "translation_id": translate_obj.id,
                        "data": translate_obj.payload,
                    }
            return Response(
                response,
                status=status.HTTP_200_OK,
            )
        else:
            return Response(
                {
                    "message": "The assigned user doesn't have permission to perform this task on translations in this project."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

    def create_transcription_task(
        self, video, user, task_type, request, eta, priority, description
    ):
        task = Task.objects.filter(video=video)
        response = self.check_duplicate_task(task_type, task, user, video)
        if len(response) > 0:
            return Response({"message": response["message"]}, status=response["status"])

        if "EDIT" in task_type:
            permitted = self.has_transcript_edit_permission(user, video)
        else:
            permitted = self.has_transcript_review_permission(user, video)

        if permitted:
            transcript = Transcript.objects.filter(video=video).first()

            if "EDIT" in task_type:
                transcript = (
                    Transcript.objects.filter(video=video)
                    .filter(status="TRANSCRIPTION_SELECT_SOURCE")
                    .first()
                )
                if transcript is None:
                    new_task = Task(
                        task_type=task_type,
                        video=video,
                        created_by=request.user,
                        user=user,
                        status="NEW",
                        eta=eta,
                        description=description,
                        priority=priority,
                    )
                    new_task.save()
                    response = {"task_id": new_task.id}
            else:
                transcript = (
                    Transcript.objects.filter(video=video)
                    .filter(status="TRANSCRIPTION_EDIT_COMPLETE")
                    .first()
                )
                if transcript is None:
                    return Response(
                        {
                            "message": "Transcript review task can't be created, as editing is not done yet."
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                else:
                    new_task = Task(
                        task_type=task_type,
                        video=video,
                        created_by=request.user,
                        user=user,
                        status="NEW",
                        eta=eta,
                        description=description,
                        priority=priority,
                    )
                    new_task.save()

                    transcript_obj = Transcript(
                        video=video,
                        user=user,
                        parent_transcript=transcript,
                        payload=transcript.payload,
                        language=video.language,
                        task=new_task,
                        transcript_type=transcript.transcript_type,
                        status="TRANSCRIPTION_REVIEWER_ASSIGNED",
                    )
                    transcript_obj.save()
                    response = {
                        "task_id": new_task.id,
                        "transcript_id": transcript_obj.id,
                        "data": transcript_obj.payload,
                    }

            return Response(
                response,
                status=status.HTTP_200_OK,
            )
        else:
            return Response(
                {
                    "message": "The assigned user doesn't have permission to perform this task on transcripts in this project."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

    def convert_payload_format(self, data):
        sentences_list = []
        if "output" in data.keys():
            payload = data["output"]
        for vtt_line in webvtt.read_buffer(StringIO(payload)):
            sentences_list.append(
                {
                    "start_time": vtt_line.start,
                    "end_time": vtt_line.end,
                    "text": vtt_line.text,
                }
            )

        return json.loads(json.dumps({"payload": sentences_list}))

    def translation_mg(self, transcript, target_language, batch_size=75):
        sentence_list = []
        vtt_output = transcript.payload
        for vtt_line in webvtt.read_buffer(StringIO(vtt_output)):
            sentence_list.append(vtt_line.text)

        all_translated_sentences = []  # List to store all the translated sentences

        # Iterate over the sentences in batch format and send them to the Translation API
        for i in range(0, len(sentence_list), batch_size):
            batch_of_input_sentences = sentence_list[i : i + batch_size]

            # Get the translation using the Indictrans NMT API
            translations_output = get_batch_translations_using_indictrans_nmt_api(
                sentence_list=batch_of_input_sentences,
                source_language=transcript.language,
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

    @swagger_auto_schema(
        method="post",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=["list_compare_sources"],
            properties={
                "list_compare_sources": openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    description="List of Sources to select from. If only one is selected, the transcript object will be created.",
                )
            },
            description="Post request body for selecting source",
        ),
        responses={
            200: "Scripts created for selected types.",
        },
    )
    @action(
        detail=True,
        methods=["POST"],
        name="Compare Sources",
        url_name="compare_sources",
    )
    def compare_sources(self, request, pk=None):
        list_compare_sources = request.data.get("list_compare_sources")
        verified_transcript = request.data.get("verified_transcript", False)

        try:
            task = Task.objects.get(pk=pk)
        except Task.DoesNotExist:
            return Response(
                {"message": "Task not found"}, status=status.HTTP_404_NOT_FOUND
            )

        if request.user != task.user:
            return Response(
                {"message": "You are not the assigned user to perform this task."},
                status=status.HTTP_403_FORBIDDEN,
            )

        if list_compare_sources is None:
            return Response(
                {"message": "missing param : list_compare_sources"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        response = {}
        payloads = {}
        if len(list_compare_sources) > 0 and request.user == task.user:
            if "TRANSCRIPT" in task.task_type:
                if "MACHINE_GENERATED" in list_compare_sources:
                    transcribed_data = make_asr_api_call(
                        task.video.url, task.video.language
                    )
                    if transcribed_data is not None:
                        data = self.convert_payload_format(transcribed_data)
                        payloads["MACHINE_GENERATED"] = data
                    else:
                        return Response(
                            {"message": "Error while calling ASR API"},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        )
                if "ORIGINAL_SOURCE" in list_compare_sources:
                    subtitles = task.video.subtitles
                    if subtitles is not None:
                        data = self.convert_payload_format(subtitles)
                        payloads["ORIGINAL_SOURCE"] = data

                if "MANUALLY_CREATED" in list_compare_sources:
                    payloads["MANUALLY_CREATED"] = json.dump(
                        request.data.get("payload", "")
                    )
            else:
                target_language = task.target_language
                if target_language is None:
                    return Response(
                        {
                            "message": "missing param : target_language required for translation"
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                response_transcript = self.check_transcript_exists(
                    task.video, verified_transcript
                )
                if type(response_transcript) == dict:
                    return Response(
                        {"message": response_transcript["message"]},
                        status=response_transcript["status"],
                    )
                else:
                    transcript = response_transcript
                response["transcript_id"] = transcript.id
                if "MACHINE_GENERATED" in list_compare_sources:
                    translation_machine_generated = self.translation_mg(
                        transcript, target_language
                    )
                    payloads["MACHINE_GENERATED"] = translation_machine_generated

                if "ORIGINAL_SOURCE" in list_compare_sources:
                    (
                        subtitle_payload,
                        is_machine_generated,
                    ) = get_subtitles_from_google_video(task.video.url, target_language)

                    if subtitle_payload is not None:
                        payloads["ORIGINAL_SOURCE"] = subtitle_payload
                if "MANUALLY_CREATED" in list_compare_sources:
                    payloads["MANUALLY_CREATED"] = request.data.get("payload", "")

            response["payloads"] = payloads
            response["task_id"] = task.id
            return Response(
                response,
                status=status.HTTP_200_OK,
            )
        else:
            return Response(
                {"message": "User is not authorized to modify this task."},
                status=status.HTTP_403_FORBIDDEN,
            )

    @swagger_auto_schema(
        method="post",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=["type", "payload"],
            properties={
                "type": openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description="Type of transcript/translation",
                ),
                "payload": openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description="payload",
                ),
            },
            description="Post request body for selecting source",
        ),
        responses={
            200: "Source has been selected",
        },
    )
    @action(
        detail=True,
        methods=["POST"],
        name="Select Source",
        url_name="select_source",
    )
    def select_source(self, request, pk=None):
        payload = request.data.get("payload")
        type = request.data.get("type")

        try:
            task = Task.objects.get(pk=pk)
        except Task.DoesNotExist:
            return Response(
                {"message": "Task not found"}, status=status.HTTP_404_NOT_FOUND
            )

        if request.user != task.user:
            return Response(
                {"message": "You are not the assigned user to perform this task."},
                status=status.HTTP_403_FORBIDDEN,
            )

        if payload is None or type is None:
            return Response(
                {"message": "missing param : payload or source_type"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if "TRANSCRIPTION" in task.task_type:
            if (
                Transcript.objects.filter(video=task.video)
                .filter(status="TRANSCRIPTION_SELECT_SOURCE")
                .first()
            ) is None:
                response = generate_transcription(
                    task.video, task.video.language, request.user, type, task, payload
                )
                task.status = "SELECTED_SOURCE"
                task.save()
            else:
                return Response(
                    {
                        "message": "Source has already been selected for this transcript."
                    },
                    status=status.HTTP_201_CREATED,
                )
        else:
            target_language = task.target_language
            if task.verified_transcript:
                transcript_status = "TRANSCRIPTION_REVIEW_COMPLETE"
            else:
                transcript_status = "TRANSCRIPTION_EDIT_COMPLETE"

            transcripts = Transcript.objects.all()

            transcript = (
                Transcript.objects.filter(video=task.video)
                .filter(status=transcript_status)
                .first()
            )

            if transcript is None:
                return Response(
                    {"message": "Transcript not found"},
                    status=status.HTTP_404_NOT_FOUND,
                )

            if target_language is None:
                return Response(
                    {
                        "message": "missing param : target_language. While creating task please select target_language"
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if (
                Translation.objects.filter(video=task.video)
                .filter(target_language=target_language)
                .filter(status="TRANSLATION_SELECT_SOURCE")
            ).first() is None:
                response = self.generate_translation(
                    task.video,
                    target_language,
                    transcript,
                    request.user,
                    type,
                    task,
                    payload,
                )
                task.status = "SELECTED_SOURCE"
                task.save()
            else:
                return Response(
                    {
                        "message": "Source has already been selected for this transcript."
                    },
                    status=status.HTTP_201_CREATED,
                )
        return Response(
            response,
            status=status.HTTP_200_OK,
        )

    def create(self, request, pk=None, *args, **kwargs):
        task_type = request.data.get("task_type")
        user_id = request.data.get("user_id")
        video_id = request.data.get("video_id")
        eta = request.data.get("eta")
        description = request.data.get("description")
        priority = request.data.get("priority")

        if task_type is None or user_id is None or video_id is None:
            return Response(
                {"message": "missing param : task_type or user_id or video_id"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        verified_transcript = False
        if "TRANSLATION" in task_type:
            target_language = request.data.get("target_language")
            if target_language is None:
                return Response(
                    {
                        "message": "missing param : target language can't be None for translation tasks"
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            verified_transcript = request.data.get("verified_transcript", False)

        try:
            video = Video.objects.get(pk=video_id)
        except Video.DoesNotExist:
            return Response(
                {"message": "Video not found"}, status=status.HTTP_404_NOT_FOUND
            )

        try:
            user = User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return Response(
                {"message": "User not found"}, status=status.HTTP_404_NOT_FOUND
            )

        if "TRANSLATION" in task_type:
            return self.create_translation_task(
                video,
                user,
                target_language,
                task_type,
                request,
                verified_transcript,
                eta,
                priority,
                description,
            )
        else:
            return self.create_transcription_task(
                video, user, task_type, request, eta, priority, description
            )

    @action(detail=False, methods=["get"], url_path="get_task_types")
    def get_task_types(self, request):
        """
        Fetches all task types.
        """
        response = [
            {"value": "TRANSLATION", "label": "Translation"},
            {"value": "TRANSCRIPTION", "label": "Transcription"},
        ]
        return Response(response, status=status.HTTP_200_OK)

    @action(detail=False, methods=["get"], url_path="get_priority_types")
    def get_priority_types(self, request):
        """
        Fetches all priority types.
        """
        data = [{"label": priority[1], "value": priority[0]} for priority in PRIORITY]
        return Response(data, status=status.HTTP_200_OK)

    @swagger_auto_schema(
        method="get",
        manual_parameters=[
            openapi.Parameter(
                "video_id",
                openapi.IN_QUERY,
                description=("An integer to identify the video"),
                type=openapi.TYPE_INTEGER,
                required=True,
            ),
            openapi.Parameter(
                "type",
                openapi.IN_QUERY,
                description=(
                    "A string to identify the type of task (TRANSCRIPT/TRANSLATION)"
                ),
                type=openapi.TYPE_STRING,
                required=True,
            ),
        ],
        responses={200: "Get allowed tasks"},
    )
    @action(detail=False, methods=["get"], url_path="get_allowed_task")
    def get_allowed_task(self, request):
        video_id = request.query_params.get("video_id")
        type = request.query_params.get("type")
        if type == "TRANSLATION":
            label = "Translation"
        else:
            label = "Transcription"
        try:
            video = Video.objects.get(pk=video_id)
        except Video.DoesNotExist:
            return Response(
                {"message": "Video not found"}, status=status.HTTP_404_NOT_FOUND
            )

        task = Task.objects.filter(video=video)
        if task.first() is None:
            response = [{"value": type + "EDIT", "label": label + " Edit"}]
        elif task.filter(task_type=type + "_EDIT").first() is None:
            response = [{"value": type + "EDIT", "label": label + " Edit"}]
        elif task.filter(task_type=type + "_EDIT").first() is not None:
            response = [{"value": type + "_REVIEW", "label": label + " Review"}]
        else:
            return Response(
                {"message": "Bad request."}, status=status.HTTP_400_BAD_REQUEST
            )
        return Response(
            response,
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=["get"], url_path="get_allowed_task")
    def get_task_status(self, request, pk=None):
        try:
            task = Video.objects.get(pk=pk)
        except Task.DoesNotExist:
            return Response(
                {"message": "Task not found"}, status=status.HTTP_404_NOT_FOUND
            )

        if (
            task.task_type == "TRANSCRIPTION_EDIT"
            or task.task_type == "TRANSLATION_EDIT"
        ):
            response = task.status
        elif (
            task.task_type == "TRANSCRIPTION_REVIEW"
            or task.task_type == "TRANSLATION_REVIEW"
        ):
            response = "EDITED"
        else:
            return Response(
                {"message": "Given task_type does not match any allowed types"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        return Response(
            response,
            status=status.HTTP_200_OK,
        )
