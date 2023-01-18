from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet
from video.models import Video
from project.decorators import is_project_owner, is_particular_project_owner
from task.decorators import has_task_edit_permission, has_task_create_permission
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
from translation.metadata import LANGUAGE_CHOICES
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

    def get_target_language_label(self, target_language):
        for language in LANGUAGE_CHOICES:
            if target_language == language[0]:
                return language[1]
        return "-"

    def get_task_type_label(self, task_type):
        for t_type in TASK_TYPE:
            if task_type == t_type[0]:
                return t_type[1]

    def get_language_pair_label(self, video, target_language):
        src_language = self.get_target_language_label(video.language)
        target_language = self.get_target_language_label(target_language)
        if target_language == "-":
            return src_language
        else:
            return src_language + "-" + target_language

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
        delete_video = []
        same_language = []

        for video in videos:
            task = Task.objects.filter(video=video)
            if target_language is not None:
                task = Task.objects.filter(video=video).filter(
                    target_language=target_language
                )
                if target_language == video.language:
                    same_language.append(video)

            if task.filter(task_type=task_type).first() is not None:
                duplicate_tasks.append(task.filter(task_type=task_type).first())

            if (
                task_type == "TRANSCRIPTION_REVIEW"
                and task.filter(task_type="TRANSLATION_EDIT").first() is not None
            ):
                delete_video.append(video)

            if (
                len(user) > 0
                and task.filter(task_type=task_type).filter(user=user[0]).first()
            ):
                if not (
                    request.user.role
                    in ["UNIVERSAL_EDITOR", "PROJECT_MANAGER", "ORG_OWNER", "ADMIN"]
                    or request.user.is_superuser
                ):
                    duplicate_user_tasks.append(
                        task.filter(task_type=task_type).filter(user=user).first()
                    )

        return duplicate_tasks, duplicate_user_tasks, delete_video, same_language

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
        is_single_task,
    ):
        (
            duplicate_tasks,
            duplicate_user_tasks,
            delete_video,
            same_language,
        ) = self.check_duplicate_tasks(
            request, task_type, target_language, user_ids, videos
        )
        response = {}
        video_ids = []
        response_tasks = []
        consolidated_error = []
        detailed_error = []
        error_duplicate_tasks = []
        error_user_tasks = []
        error_same_language_tasks = []

        if len(duplicate_tasks) > 0:
            for task in duplicate_tasks:
                video_ids.append(task.video)
                error_duplicate_tasks.append(
                    {"video": task.video, "task_type": task.task_type}
                )

        if len(duplicate_user_tasks) > 0:
            for task in duplicate_user_tasks:
                video_ids.append(task.video)
                error_user_tasks.append({"video": task.video, "task_type": task_type})

        if len(same_language) > 0:
            for video in same_language:
                video_ids.append(video)
                error_same_language_tasks.append(
                    {"video": video, "task_type": task_type}
                )

        for video in video_ids:
            videos.remove(video)
            if len(user_ids) > 0:
                del user_ids[-1]

        if len(duplicate_user_tasks):
            consolidated_error.append(
                {
                    "message": "Tasks creation failed as same user can't be Editor and Reviewer.",
                    "count": len(error_user_tasks),
                }
            )
            for task in error_user_tasks:
                detailed_error.append(
                    {
                        "video_name": task["video"].name,
                        "video_url": task["video"].url,
                        "task_type": self.get_task_type_label(task["task_type"]),
                        "language_pair": self.get_language_pair_label(
                            task["video"], target_language
                        ),
                        "status": "Fail",
                        "message": "This task creation failed since Editor and Reviewer can't be same.",
                    }
                )

        if len(error_same_language_tasks):
            consolidated_error.append(
                {
                    "message": "Task creation failed as target language is same as source language.",
                    "count": len(error_same_language_tasks),
                }
            )
            for task in error_same_language_tasks:
                detailed_error.append(
                    {
                        "video_name": task["video"].name,
                        "video_url": task["video"].url,
                        "task_type": self.get_task_type_label(task["task_type"]),
                        "language_pair": self.get_language_pair_label(
                            task["video"], target_language
                        ),
                        "status": "Fail",
                        "message": "Task creation failed as target language is same as source language.",
                    }
                )

        if len(duplicate_tasks):
            consolidated_error.append(
                {
                    "message": "Task creation failed as tasks already exists for the selected videos.",
                    "count": len(error_duplicate_tasks),
                }
            )
            for task in error_duplicate_tasks:
                detailed_error.append(
                    {
                        "video_name": task["video"].name,
                        "video_url": task["video"].url,
                        "task_type": self.get_task_type_label(task["task_type"]),
                        "language_pair": self.get_language_pair_label(
                            task["video"], target_language
                        ),
                        "status": "Fail",
                        "message": "Task creation failed as selected task already exist.",
                    }
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
                    detailed_error.append(
                        {
                            "video_name": task.video.name,
                            "video_url": task.video.url,
                            "task_type": self.get_task_type_label(task.task_type),
                            "language_pair": self.get_language_pair_label(
                                task["video"], target_language
                            ),
                            "status": "Successful",
                            "message": "Task is successfully created.",
                        }
                    )
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
                        status="NEW",
                        eta=eta,
                        description=description,
                        priority=priority,
                        is_active=is_active,
                    )
                    new_task.save()
                    tasks.append(new_task)

                new_translations = []
                for task in tasks:
                    detailed_error.append(
                        {
                            "video_name": task.video.name,
                            "video_url": task.video.url,
                            "task_type": self.get_task_type_label(task.task_type),
                            "language_pair": task.get_language_pair_label,
                            "status": "Successful",
                            "message": "Task is successfully created.",
                        }
                    )
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

            if len(tasks) > 0:
                consolidated_error.append(
                    {"message": "Tasks created successfully.", "count": len(tasks)}
                )

            message = ""
            if len(video_ids) > 0:
                message = "{0} Task(s) creation failed.".format(len(video_ids))
            if len(tasks) > 0:
                message = (
                    "{0} Task(s) created successfully.".format(len(tasks)) + message
                )
            response = {
                "consolidated_report": consolidated_error,
                "detailed_report": detailed_error,
            }

            if is_single_task:
                if detailed_error[0]["status"] == "Fail":
                    status_code = status.HTTP_400_BAD_REQUEST
                else:
                    status_code = status.HTTP_200_OK
                return Response(
                    {"message": detailed_error[0]["message"]},
                    status=status_code,
                )
            return Response(
                {"message": message, "response": response},
                status=status.HTTP_207_MULTI_STATUS,
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
        is_single_task,
    ):
        (
            duplicate_tasks,
            duplicate_user_tasks,
            delete_video,
            same_language,
        ) = self.check_duplicate_tasks(request, task_type, None, user_ids, videos)

        response = {}
        video_ids = []
        response_tasks = []
        consolidated_error = []
        detailed_error = []
        error_duplicate_tasks = []
        error_user_tasks = []
        error_review_tasks = []

        if len(duplicate_tasks) > 0:
            for task in duplicate_tasks:
                video_ids.append(task.video)
                error_duplicate_tasks.append(
                    {"video": task.video, "task_type": task.task_type}
                )

        if len(duplicate_user_tasks) > 0:
            for task in duplicate_user_tasks:
                video_ids.append(task.video)
                error_user_tasks.append({"video": task.video, "task_type": task_type})

        if len(delete_video) > 0:
            for video in delete_video:
                video_ids.append(video)
                error_review_tasks.append({"video": video, "task_type": task_type})

        for video in video_ids:
            videos.remove(video)
            if len(user_ids) > 0:
                del user_ids[-1]

        if len(duplicate_user_tasks):
            consolidated_error.append(
                {
                    "message": "Tasks creation failed as same user can't be editor and reviewer.",
                    "count": len(error_user_tasks),
                }
            )
            detailed_response = []
            for task in error_user_tasks:
                detailed_error.append(
                    {
                        "video_name": task["video"].name,
                        "video_url": task["video"].url,
                        "task_type": self.get_task_type_label(task["task_type"]),
                        "language_pair": self.get_language_pair_label(
                            task["video"], ""
                        ),
                        "status": "Fail",
                        "message": "This task creation failed since Editor and Reviewer can't be same.",
                    }
                )

        if len(duplicate_tasks):
            consolidated_error.append(
                {
                    "message": "Task creation failed as this task already exists for selected videos.",
                    "count": len(error_duplicate_tasks),
                }
            )
            for task in error_duplicate_tasks:
                detailed_error.append(
                    {
                        "video_name": task["video"].name,
                        "video_url": task["video"].url,
                        "task_type": self.get_task_type_label(task["task_type"]),
                        "language_pair": self.get_language_pair_label(
                            task["video"], ""
                        ),
                        "status": "Fail",
                        "message": "Task creation failed as selected task already exist.",
                    }
                )

        if len(error_review_tasks) > 0:
            consolidated_error.append(
                {
                    "message": "Task creation for Transcription Review failed as Translation tasks already exists.",
                    "count": len(error_review_tasks),
                }
            )
            for task in error_review_tasks:
                detailed_error.append(
                    {
                        "video_name": task["video"].name,
                        "video_url": task["video"].url,
                        "task_type": self.get_task_type_label(task["task_type"]),
                        "language_pair": self.get_language_pair_label(
                            task["video"], ""
                        ),
                        "status": "Fail",
                        "message": "Task creation for Transcription Review failed as Translation tasks already exists.",
                    }
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
                delete_tasks = []
                asr_errors = 0
                for task in tasks:
                    payloads = self.generate_transcript_payload(task, [source_type])
                    if type(payloads) != dict:
                        asr_errors += 1
                        detailed_error.append(
                            {
                                "video_name": task.video.name,
                                "video_url": task.video.url,
                                "task_type": self.get_task_type_label(task.task_type),
                                "language_pair": task.get_language_pair_label,
                                "status": "Fail",
                                "message": "Error while calling ASR API.",
                            }
                        )
                        videos.remove(task.video)
                        video_ids.append(task.video)
                        delete_tasks.append(task)
                        consolidated_error.append(
                            {
                                "message": "Error while calling ASR API.",
                                "count": asr_errors,
                            }
                        )
                        continue
                    detailed_error.append(
                        {
                            "video_name": task.video.name,
                            "video_url": task.video.url,
                            "task_type": self.get_task_type_label(task.task_type),
                            "language_pair": task.get_language_pair_label,
                            "status": "Successful",
                            "message": "Task created successfully.",
                        }
                    )
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
                    detailed_error.append(
                        {
                            "video_name": task.video.name,
                            "video_url": task.video.url,
                            "task_type": self.get_task_type_label(task.task_type),
                            "status": "Successful",
                            "language_pair": task.get_language_pair_label,
                            "message": "Task is successfully created.",
                        }
                    )
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

            for task in delete_tasks:
                task.delete()
                tasks.remove(task)

            if len(tasks) > 0:
                consolidated_error.append(
                    {"message": "Tasks created successfully.", "count": len(tasks)}
                )
            message = ""
            if len(video_ids) > 0:
                message = "{0} Task(s) creation failed.".format(len(video_ids))
            if len(tasks) > 0:
                message = (
                    "{0} Task(s) created successfully.".format(len(tasks)) + message
                )
            response = {
                "consolidated_report": consolidated_error,
                "detailed_report": detailed_error,
            }
            if is_single_task:
                if detailed_error[0]["status"] == "Fail":
                    status_code = status.HTTP_400_BAD_REQUEST
                else:
                    status_code = status.HTTP_200_OK
                return Response(
                    {"message": detailed_error[0]["message"]},
                    status=status_code,
                )
            return Response(
                {"message": message, "response": response},
                status=status.HTTP_207_MULTI_STATUS,
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

        payloads = {}
        if len(list_compare_sources) > 0 and request.user == task.user:
            if "TRANSCRIPT" in task.task_type:
                payloads = self.generate_transcript_payload(task, list_compare_sources)
                if type(payloads) != dict:
                    return Response(
                        {"message": "Error while calling ASR API"},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
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

                transcript = self.check_transcript_exists(task.video)

                if type(transcript) == dict:
                    return Response(
                        {"message": "Transcript doesn't exist for this video."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                payloads = generate_translation_payload(
                    transcript, target_language, list_compare_sources
                )
            response = {}
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

    @swagger_auto_schema(
        method="DELETE",
        manual_parameters=[
            openapi.Parameter(
                "flag",
                openapi.IN_QUERY,
                description=("A boolean to force delete the translation tasks."),
                type=openapi.TYPE_BOOLEAN,
                required=False,
            ),
        ],
        responses={409: "There are conflicts with this task."},
    )
    @has_task_edit_permission
    @action(detail=True, methods=["delete"], url_path="delete_task")
    def delete_task(self, request, pk=None, *args, **kwargs):
        try:
            task = Task.objects.get(pk=pk)
        except Task.DoesNotExist:
            return Response(
                {"message": "Task not found"}, status=status.HTTP_404_NOT_FOUND
            )
        translation_tasks = set()
        flag = request.query_params.get("flag")

        if task.task_type in ["TRANSCRIPTION_EDIT", "TRANSCRIPTION_REVIEW"]:
            transcripts = Transcript.objects.filter(video=task.video)

            if "REVIEW" in task.task_type:
                tasks_to_delete = [
                    transcript.task
                    for transcript in transcripts.filter(task=task).all()
                ]
            else:
                tasks_to_delete = [transcript.task for transcript in transcripts]

            for transcript in transcripts.all():
                for translation in Translation.objects.filter(video=task.video).all():
                    translation_tasks.add(translation.task)

            if len(translation_tasks) > 0:
                response = [
                    {
                        "task_type": translation_task.get_task_type_label,
                        "target_language": translation_task.get_target_language_label,
                        "video_name": translation_task.video.name,
                        "id": translation_task.id,
                    }
                    for translation_task in translation_tasks
                ]

                if flag == "true":
                    for task in translation_tasks:
                        task.delete()
                    for task in tasks_to_delete:
                        task.delete()
                else:
                    return Response(
                        {
                            "response": response,
                            "message": "The Transcription task has dependent translation tasks. Do you still want to delete all related translations as well?.",
                        },
                        status=status.HTTP_409_CONFLICT,
                    )
            else:
                for task in tasks_to_delete:
                    task.delete()

        if task.task_type == "TRANSLATION_EDIT":
            translations = (
                Translation.objects.filter(video=task.video)
                .filter(target_language=task.target_language)
                .all()
            )
            tasks_to_delete = [translation.task for translation in translations]
            for task in list(set(tasks_to_delete)):
                task.delete()

        if task.task_type == "TRANSLATION_REVIEW":
            task.delete()

        return Response(
            {
                "message": "Task is deleted, with all associated transcripts/translations"
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

        if "is_single_task" in request.data.keys():
            is_single_task = request.data.get("is_single_task")
        else:
            is_single_task = False

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

        permission = has_task_create_permission(videos[0], request.user)

        if type(permission) != bool:
            return permission

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
            user_ids = [user for i in range(len(videos))]
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
                is_single_task,
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
                is_single_task,
            )

    @has_task_edit_permission
    def partial_update(self, request, pk=None, *args, **kwargs):
        user = request.data.get("user")
        description = request.data.get("description")
        eta = request.data.get("eta")
        priority = request.data.get("priority")

        try:
            task = Task.objects.get(pk=pk)
        except Task.DoesNotExist:
            return Response(
                {"message": "Task not found"}, status=status.HTTP_404_NOT_FOUND
            )

        if user is not None:
            try:
                user_obj = User.objects.get(pk=user)
            except User.DoesNotExist:
                return Response(
                    {"message": "User not found"}, status=status.HTTP_404_NOT_FOUND
                )

            if task.task_type == "TRANSCRIPTION_EDIT":
                permission = self.has_transcript_edit_permission(user_obj, [task.video])
            elif task.task_type == "TRANSCRIPTION_REVIEW":
                permission = self.has_transcript_review_permission(
                    user_obj, [task.video]
                )
            elif task.task_type == "TRANSLATION_EDIT":
                permission = self.has_translate_edit_permission(user_obj, [task.video])
            elif task.task_type == "TRANSLATION_REVIEW":
                permission = self.has_translate_review_permission(
                    user_obj, [task.video]
                )
            else:
                print("Not a Valid Type")

            if permission:
                task.user = user_obj
            else:
                return Response(
                    {
                        "message": "The assigned user is not allowed to perform this task in this project."
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

        if priority is not None:
            task.priority = priority

        if eta is not None:
            task.eta = eta

        if description is not None:
            task.description = description

        task.save()
        return Response(
            {"message": "Task is successfully updated."},
            status=status.HTTP_200_OK,
        )

    @has_task_edit_permission
    @action(detail=False, methods=["patch"], url_path="update_multiple_tasks")
    def put(self, request, *args, **kwargs):
        task_ids = request.data.get("task_ids")
        user = request.data.get("user")
        description = request.data.get("description")
        eta = request.data.get("eta")
        priority = request.data.get("priority")
        not_permitted_users = []

        for task_id in task_ids:
            try:
                task = Task.objects.get(pk=task_id)
            except Task.DoesNotExist:
                return Response(
                    {"message": "Task not found"}, status=status.HTTP_404_NOT_FOUND
                )

            if user is not None:
                try:
                    user_obj = User.objects.get(pk=user)
                except User.DoesNotExist:
                    return Response(
                        {"message": "User not found"}, status=status.HTTP_404_NOT_FOUND
                    )

                if task.task_type == "TRANSCRIPTION_EDIT":
                    permission = self.has_transcript_edit_permission(
                        user_obj, [task.video]
                    )
                elif task.task_type == "TRANSCRIPTION_REVIEW":
                    permission = self.has_transcript_review_permission(
                        user_obj, [task.video]
                    )
                elif task.task_type == "TRANSLATION_EDIT":
                    permission = self.has_translate_edit_permission(
                        user_obj, [task.video]
                    )
                elif task.task_type == "TRANSLATION_REVIEW":
                    permission = self.has_translate_review_permission(
                        user_obj, [task.video]
                    )
                else:
                    print("Not a Valid Type")

                if permission:
                    task.user = user_obj
                else:
                    not_permitted_users.append(task_id)
                    continue

            if priority is not None:
                task.priority = priority

            if eta is not None:
                task.eta = eta

            if description is not None:
                task.description = description

            task.save()
        if len(not_permitted_users) > 0:
            return Response(
                {
                    "message": "The assigned user is not allowed to perform these tasks.{0}".format(
                        not_permitted_users
                    )
                },
                status=status.HTTP_403_FORBIDDEN,
            )
        return Response(
            {
                "message": "Task updated successfully.",
            },
            status=status.HTTP_200_OK,
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
            {"id": 1, "value": "TRANSCRIPTION_EDIT", "label": "Transcription Edit"},
            {"id": 2, "value": "TRANSCRIPTION_REVIEW", "label": "Transcription Review"},
            {"id": 3, "value": "TRANSLATION_EDIT", "label": "Translation Edit"},
            {"id": 4, "value": "TRANSLATION_REVIEW", "label": "Translation Review"},
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
