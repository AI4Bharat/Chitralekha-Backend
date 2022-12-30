from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet
from video.models import Video
from project.decorators import is_project_owner
from project.models import Project
from organization.models import Organization
from transcript.views import generate_transcription
from rest_framework.decorators import action
from users.models import User
from transcript.utils.asr import get_asr_supported_languages, make_asr_api_call
from transcript.models import Transcript
from translation.models import Translation
from django.db.models import Count
from translation.utils import (
    get_batch_translations_using_indictrans_nmt_api,
    generate_translation_payload,
    translation_mg,
)
from video.utils import get_subtitles_from_google_video
from rest_framework.permissions import IsAuthenticated
import webvtt
from io import StringIO
import json, sys
from config import *


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

    def has_transcript_edit_permission(self, user, videos):
        if user in videos[0].project_id.members.all() and (
            user.role == User.TRANSCRIPT_EDITOR
            or user.role == User.UNIVERSAL_EDITOR
            or user.role == User.TRANSCRIPT_REVIEWER
            or user.role == User.PROJECT_MANAGER
            or user.role == User.ORG_OWNER
            or user.role == User.ADMIN
            or user.is_superuser
        ):
            return True
        return False

    def has_transcript_review_permission(self, user, videos):
        if user in videos[0].project_id.members.all() and (
            user.role == User.UNIVERSAL_EDITOR
            or user.role == User.TRANSCRIPT_REVIEWER
            or user.role == User.PROJECT_MANAGER
            or user.role == User.ORG_OWNER
            or user.role == User.ADMIN
            or user.is_superuser
        ):
            return True
        return False

    def has_translate_edit_permission(self, user, videos):
        if user in videos[0].project_id.members.all() and (
            user.role == User.UNIVERSAL_EDITOR
            or user.role == User.TRANSLATION_EDITOR
            or user.role == User.TRANSLATION_REVIEWER
            or user.role == User.PROJECT_MANAGER
            or user.role == User.ORG_OWNER
            or user.role == User.ADMIN
            or user.is_superuser
        ):
            return True
        return False

    def has_translate_review_permission(self, user, videos):
        if user in videos[0].project_id.members.all() and (
            user.role == User.UNIVERSAL_EDITOR
            or user.role == User.TRANSLATION_REVIEWER
            or user.role == User.PROJECT_MANAGER
            or user.role == User.ORG_OWNER
            or user.role == User.ADMIN
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

    def check_duplicate_tasks(self, request, task_type, target_language, user, videos):
        duplicate_tasks = []
        duplicate_user_tasks = []
        for video in videos:
            task = Task.objects.filter(video=video)
            if target_language is not None:
                task = Task.objects.filter(video=video).filter(
                    target_language=target_language
                )

            if task.filter(task_type=task_type).first() is not None:
                duplicate_tasks.append(task.filter(task_type=task_type).first())

            """
            if task.filter(task_type=task_type).filter(user=user).first():
                if not (request.user.role > 4 or request.user.is_superuser):
                    duplicate_user_tasks.append(
                        task.filter(task_type=task_type).filter(user=user).first()
                    )
            """
        return duplicate_tasks, duplicate_user_tasks

    def check_transcript_exists(self, video):
        transcript = Transcript.objects.filter(video=video)

        if (
            transcript.filter(status="TRANSCRIPTION_REVIEW_COMPLETE").first()
            is not None
        ):
            return transcript.filter(status="TRANSCRIPTION_REVIEW_COMPLETE").first()
        elif (
            transcript.filter(status="TRANSCRIPTION_EDIT_COMPLETE").first() is not None
        ):
            return transcript.filter(status="TRANSCRIPTION_EDIT_COMPLETE").first()
        else:
            return {
                "message": "Transcript doesn't exist for this video.",
                "status": status.HTTP_400_BAD_REQUEST,
            }

    def create_translation_task(
        self,
        videos,
        user_ids,
        target_language,
        task_type,
        source_type,
        request,
        eta,
        priority,
        description,
    ):
        duplicate_tasks, duplicate_user_tasks = self.check_duplicate_tasks(
            request, task_type, target_language, user_ids, videos
        )
        response = {}
        if len(duplicate_tasks) > 0 or len(duplicate_user_tasks) > 0:
            video_ids = [task.video for task in duplicate_tasks] + [
                task.video for task in duplicate_user_tasks
            ]
            for video in video_ids:
                videos.remove(video)
                if len(user_ids) > 0:
                    del user_ids[-1]

            if len(videos) <= 0:
                return Response(
                    {"message": "This task is already created for selected videos."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        if len(user_ids) > 0:
            if "EDIT" in task_type:
                permitted = self.has_translate_edit_permission(user_ids[0], videos)
            else:
                permitted = self.has_translate_review_permission(user_ids[0], videos)
        else:
            permitted = True

        if permitted:
            if "EDIT" in task_type:
                tasks = []
                for video in videos:
                    if len(user_ids) == 0:
                        user_id = self.assign_users(task_type, video.project_id)
                        if user_id is None:
                            user = request.user
                        else:
                            user = User.objects.get(pk=user_id)
                    else:
                        user = user_ids[0]
                    transcript = self.check_transcript_exists(video)

                    if type(transcript) == dict:
                        is_active = False
                    else:
                        is_active = True

                    new_task = Task(
                        task_type=task_type,
                        video=video,
                        created_by=request.user,
                        user=user,
                        target_language=target_language,
                        status="SELECTED_SOURCE",
                        eta=eta,
                        description=description,
                        priority=priority,
                        is_active=is_active,
                    )
                    new_task.save()
                    tasks.append(new_task)

                new_translations = []
                for task in tasks:
                    if task.is_active:
                        transcript = self.check_transcript_exists(task.video)
                        payloads = generate_translation_payload(
                            transcript, target_language, [source_type]
                        )
                    else:
                        payloads = {source_type: ""}
                        transcript = None
                    translate_obj = Translation(
                        video=task.video,
                        user=task.user,
                        transcript=transcript,
                        payload=payloads[source_type],
                        target_language=target_language,
                        task=task,
                        translation_type=source_type,
                        status="TRANSLATION_SELECT_SOURCE",
                    )
                    new_translations.append(translate_obj)
                translations = Translation.objects.bulk_create(new_translations)
            else:
                tasks = []
                for video in videos:
                    if len(user_ids) == 0:
                        user_id = self.assign_users(task_type, video.project_id)
                        if user_id is None:
                            user = request.user
                        else:
                            user = User.objects.get(pk=user_id)
                    else:
                        user = user_ids[0]

                    translation = (
                        Translation.objects.filter(video=video)
                        .filter(status="TRANSLATION_EDIT_COMPLETE")
                        .filter(target_language=target_language)
                        .first()
                    )
                    is_active = False
                    if translation is not None:
                        is_active = True
                    new_task = Task(
                        task_type=task_type,
                        video=video,
                        created_by=request.user,
                        user=user,
                        target_language=target_language,
                        status="SELECTED_SOURCE",
                        eta=eta,
                        description=description,
                        priority=priority,
                        is_active=is_active,
                    )
                    new_task.save()
                    tasks.append(new_task)

                new_translations = []
                for task in tasks:
                    translation = (
                        Translation.objects.filter(video=task.video)
                        .filter(status="TRANSLATION_EDIT_COMPLETE")
                        .filter(target_language=target_language)
                        .first()
                    )

                    if translation is not None:
                        payload = translation.payload
                        transcript = translation.transcript
                        is_active = True
                    else:
                        payload = None
                        transcript = None
                        is_active = False
                    translate_obj = Translation(
                        video=task.video,
                        user=task.user,
                        transcript=transcript,
                        parent=translation,
                        payload=payload,
                        target_language=target_language,
                        task=new_task,
                        translation_type=source_type,
                        status="TRANSLATION_REVIEWER_ASSIGNED",
                    )
                    new_translations.append(translate_obj)
                translations = Translation.objects.bulk_create(new_translations)

            response["message"] = "Translation task is created"
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
        self,
        videos,
        user_ids,
        task_type,
        source_type,
        request,
        eta,
        priority,
        description,
    ):
        duplicate_tasks, duplicate_user_tasks = self.check_duplicate_tasks(
            request, task_type, None, user_ids, videos
        )
        response = {}
        if len(duplicate_tasks) > 0 or len(duplicate_user_tasks) > 0:
            video_ids = [task.video for task in duplicate_tasks] + [
                task.video for task in duplicate_user_tasks
            ]
            for video in video_ids:
                videos.remove(video)
                if len(user_ids) > 0:
                    del user_ids[-1]

            if len(videos) <= 0:
                return Response(
                    {"message": "This task is already created for selected videos."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        if len(user_ids) > 0:
            if "EDIT" in task_type:
                permitted = self.has_transcript_edit_permission(user_ids[0], videos)
            else:
                permitted = self.has_transcript_review_permission(user_ids[0], videos)
        else:
            permitted = True

        if permitted:
            if "EDIT" in task_type:
                tasks = []
                for video in videos:
                    if len(user_ids) == 0:
                        user_id = self.assign_users(task_type, video.project_id)
                        if user_id is None:
                            user = request.user
                        else:
                            user = User.objects.get(pk=user_id)
                    else:
                        user = user_ids[0]
                    new_task = Task(
                        task_type=task_type,
                        video=video,
                        created_by=request.user,
                        user=user,
                        status="SELECTED_SOURCE",
                        eta=eta,
                        description=description,
                        priority=priority,
                        is_active=True,
                    )
                    new_task.save()
                    tasks.append(new_task)

                new_transcripts = []
                for task in tasks:
                    payloads = self.generate_transcript_payload(task, [source_type])
                    transcript_obj = Transcript(
                        video=task.video,
                        user=task.user,
                        payload=payloads[source_type],
                        language=task.video.language,
                        task=task,
                        transcript_type=source_type,
                        status="TRANSCRIPTION_SELECT_SOURCE",
                    )
                    new_transcripts.append(transcript_obj)
                transcripts = Transcript.objects.bulk_create(new_transcripts)
            else:
                tasks = []
                for video in videos:
                    transcript = (
                        Transcript.objects.filter(video=video)
                        .filter(status="TRANSCRIPTION_EDIT_COMPLETE")
                        .first()
                    )
                    is_active = False
                    if transcript is not None:
                        is_active = True

                    if len(user_ids) == 0:
                        user_id = self.assign_users(task_type, video.project_id)
                        if user_id is None:
                            user = request.user
                        else:
                            user = User.objects.get(pk=user_id)
                    else:
                        user = user_ids[0]

                    new_task = Task(
                        task_type=task_type,
                        video=video,
                        created_by=request.user,
                        user=user,
                        status="NEW",
                        eta=eta,
                        description=description,
                        priority=priority,
                        is_active=is_active,
                    )
                    new_task.save()
                    tasks.append(new_task)

                new_transcripts = []
                for task in tasks:
                    if task.is_active:
                        payload = transcript.payload
                        transcript_type = transcript.transcript_type
                    else:
                        payload = None
                        transcript_type = None
                    transcript_obj = Transcript(
                        video=task.video,
                        user=task.user,
                        parent_transcript=transcript,
                        payload=payload,
                        language=task.video.language,
                        task=task,
                        transcript_type=source_type,
                        status="TRANSCRIPTION_REVIEWER_ASSIGNED",
                    )
                    new_transcripts.append(transcript_obj)
                transcripts = Transcript.objects.bulk_create(new_transcripts)

            return Response(
                {"message": "Transcript task is created"},
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

    def generate_transcript_payload(self, task, list_compare_sources):
        payloads = {}
        if "MACHINE_GENERATED" in list_compare_sources:
            transcribed_data = make_asr_api_call(task.video.url, task.video.language)
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
            else:
                payloads["ORIGINAL_SOURCE"] = {"payload": []}

        if "MANUALLY_CREATED" in list_compare_sources:
            payloads["MANUALLY_CREATED"] = {"payload": []}
        return payloads

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
                payloads = self.generate_transcript_payload(task, list_compare_sources)
            else:
                target_language = task.target_language
                if target_language is None:
                    return Response(
                        {
                            "message": "missing param : target_language required for translation"
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                transcript = self.check_transcript_exists(task.video)

                if type(transcript) == dict:
                    return Response(
                        {"message": "Transcript doesn't exist for this video."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                payloads = generate_translation_payload(
                    transcript, target_language, list_compare_sources
                )

            response["payloads"] = payloads
            response["task_id"] = task.id
            response["message"] = "Payloads are generated for selected option."
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
                    type=openapi.TYPE_OBJECT,
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
        source_type = request.data.get("type")

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

        if payload is None or source_type is None:
            return Response(
                {"message": "missing param : payload or source_type"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if "TRANSCRIPTION" in task.task_type:
            transcription = (
                Transcript.objects.filter(video=task.video)
                .filter(status="TRANSCRIPTION_SELECT_SOURCE")
                .first()
            )
            if transcription is not None:
                if source_type != transcription.transcript_type:
                    transcription.delete()
                else:
                    response = {}
                    response["transcript_id"] = transcription.id
                    response["message"] = "Source is selected successfully."
                    return Response(
                        response,
                        status=status.HTTP_200_OK,
                    )
            response = generate_transcription(
                task.video,
                task.video.language,
                request.user,
                source_type,
                task,
                payload,
            )
            task.status = "SELECTED_SOURCE"
            task.save()

        else:
            target_language = task.target_language
            translation = (
                Translation.objects.filter(video=task.video)
                .filter(target_language=target_language)
                .filter(status="TRANSLATION_SELECT_SOURCE")
                .first()
            )
            if translation is not None:
                if source_type != translation.translation_type:
                    translation.delete()
                else:
                    response = {}
                    response["translation_id"] = translation.id
                    response["message"] = "Source is selected successfully."
                    return Response(
                        response,
                        status=status.HTTP_200_OK,
                    )

            transcript = self.check_transcript_exists(task.video)
            if type(transcript) == dict:
                return Response(
                    {"message": transcript["message"]},
                    status=transcript["status"],
                )

            response = self.generate_translation(
                task.video,
                target_language,
                transcript,
                request.user,
                source_type,
                task,
                payload,
            )
            task.status = "SELECTED_SOURCE"
            task.save()
        response["message"] = "Selection of source is successful."
        return Response(
            response,
            status=status.HTTP_200_OK,
        )

    @is_project_owner
    def destroy(self, request, pk=None, *args, **kwargs):
        task = Task.objects.get(pk=pk)
        translation_tasks = set()
        if "TRANSCRIPT" in task.task_type:
            for transcript in Transcript.objects.filter(task=task).all():
                for translation in Translation.objects.filter(
                    transcript=transcript
                ).all():
                    translation_tasks.add(translation.task)

        if len(translation_tasks) > 0:
            response = [
                (
                    translation_task.task_type,
                    translation_task.target_language,
                    translation_task.video.name,
                )
                for translation_task in translation_tasks
            ]

            return Response(
                {
                    "response": response,
                    "message": "Transcription Task can't be deleted as there are associated Translation tasks. Please delete the translation tasks first.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        task.delete()
        return Response(
            {
                "message": "Task is deleted , with all associated transcripts/translations"
            },
            status=status.HTTP_200_OK,
        )

    def assign_users(self, task_type, project):
        videos = Video.objects.filter(project_id=project)
        roles = allowed_roles[task_type]
        users = (
            User.objects.filter(id__in=project.members.all())
            .filter(role__in=roles)
            .values_list("id", flat=True)
        )
        sorted_users = (
            Task.objects.filter(video_id__in=videos)
            .filter(user_id__in=users)
            .values_list("user", flat=True)
            .annotate(count=Count("user"))
            .order_by("count", "user__email")
        )
        user_with_zero_tasks = set(list(users)) - set(list(sorted_users))

        if len(user_with_zero_tasks) > 0:
            return list(user_with_zero_tasks)[0]
        if len(sorted_users) > 0:
            return sorted_users[0]
        return None

    @is_project_owner
    def create(self, request, pk=None, *args, **kwargs):
        task_type = request.data.get("task_type")
        user_id = request.data.get("user_id")
        video_ids = request.data.get("video_ids")
        eta = request.data.get("eta")
        description = request.data.get("description")
        priority = request.data.get("priority")

        if task_type is None or video_ids is None or len(video_ids) == 0:
            return Response(
                {"message": "missing param : task_type or user_id or video_ids"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if "TRANSLATION" in task_type:
            target_language = request.data.get("target_language")
            if target_language is None:
                return Response(
                    {
                        "message": "missing param : target language can't be None for translation tasks"
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

        videos = []
        for video_id in video_ids:
            try:
                video = Video.objects.get(pk=video_id)
            except Video.DoesNotExist:
                return Response(
                    {"message": "Video not found"}, status=status.HTTP_404_NOT_FOUND
                )
            videos.append(video)

        project = videos[0].project_id
        organization = project.organization_id

        user_ids = []
        if user_id is not None:
            try:
                user = User.objects.get(pk=user_id)
            except User.DoesNotExist:
                return Response(
                    {"message": "User not found"}, status=status.HTTP_404_NOT_FOUND
                )
            user_ids = [user_id for i in range(len(videos))]

        if "TRANSLATION" in task_type:
            source_type = (
                project.default_translation_type
                or organization.default_translation_type
            )
            if source_type == None:
                source_type = backend_default_translation_type
            return self.create_translation_task(
                videos,
                user_ids,
                target_language,
                task_type,
                source_type,
                request,
                eta,
                priority,
                description,
            )
        else:
            source_type = (
                project.default_transcript_type or organization.default_transcript_type
            )
            if source_type == None:
                source_type = backend_default_transcript_type
            return self.create_transcription_task(
                videos,
                user_ids,
                task_type,
                source_type,
                request,
                eta,
                priority,
                description,
            )

    @action(detail=False, methods=["get"], url_path="get_task_types")
    def get_task_types(self, request):
        """
        Fetches all task types.
        """
        response = [
            {"value": "TRANSCRIPTION", "label": "Transcription"},
            {"value": "TRANSLATION", "label": "Translation"},
        ]
        return Response(response, status=status.HTTP_200_OK)

    @action(detail=False, methods=["get"], url_path="get_bulk_task_types")
    def get_bulk_task_types(self, request):
        """
        Fetches all task types.
        """
        response = [
            {"value": "TRANSCRIPTION_EDIT", "label": "Transcription Edit"},
            {"value": "TRANSCRIPTION_REVIEW", "label": "Transcription Review"},
            {"value": "TRANSLATION_EDIT", "label": "Translation Edit"},
            {"value": "TRANSLATION_REVIEW", "label": "Translation Review"},
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
            openapi.Parameter(
                "target_language",
                openapi.IN_QUERY,
                description=("A string to get the language of translation"),
                type=openapi.TYPE_STRING,
                required=False,
            ),
        ],
        responses={200: "Get allowed tasks"},
    )
    @action(detail=False, methods=["get"], url_path="get_allowed_task")
    def get_allowed_task(self, request):
        video_id = request.query_params.get("video_id")
        type = request.query_params.get("type")
        if type == "TRANSLATION":
            target_language = request.query_params.get("target_language")
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

        if request.query_params.get("target_language") is not None:
            task = Task.objects.filter(video=video).filter(
                target_language=target_language
            )

        if task.first() is None:
            response = [{"value": type + "_EDIT", "label": "Edit"}]
        elif task.filter(task_type=type + "_EDIT").first() is None:
            response = [{"value": type + "_EDIT", "label": "Edit"}]
        elif task.filter(task_type=type + "_EDIT").first() is not None:
            response = [{"value": type + "_REVIEW", "label": "Review"}]
        else:
            return Response(
                {"message": "Bad request."}, status=status.HTTP_400_BAD_REQUEST
            )
        return Response(
            response,
            status=status.HTTP_200_OK,
        )
