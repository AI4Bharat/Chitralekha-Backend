from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet
from video.models import Video
from project.decorators import is_project_owner, is_particular_project_owner
from task.decorators import (
    has_task_edit_permission,
    has_task_create_permission,
    has_task_edit_permission_individual,
)
from project.models import Project
from organization.models import Organization
from transcript.views import generate_transcription
from rest_framework.decorators import action
from users.models import User
from transcript.utils.asr import get_asr_supported_languages, make_asr_api_call
from voiceover.utils import (
    generate_voiceover_payload,
    process_translation_payload,
    send_mail_to_user,
    get_bad_sentences,
    get_bad_sentences_in_progress,
)
from transcript.models import (
    Transcript,
    MANUALLY_UPLOADED,
    TRANSCRIPTION_SELECT_SOURCE,
    TRANSCRIPTION_EDIT_COMPLETE,
)
from translation.models import Translation, TRANSLATION_SELECT_SOURCE
from django.db.models import Count, Q
from translation.utils import (
    get_batch_translations_using_indictrans_nmt_api,
    generate_translation_payload,
    translation_mg,
)
from voiceover.models import VoiceOver
from rest_framework.permissions import IsAuthenticated
import webvtt
from io import StringIO
import json, sys
from config import *
from translation.metadata import TRANSLATION_LANGUAGE_CHOICES
from voiceover.metadata import VOICEOVER_SUPPORTED_LANGUAGES
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
import logging
import io
import zipfile
from django.http import HttpResponse
import datetime
from task.tasks import (
    celery_asr_call,
    celery_tts_call,
    celery_nmt_call,
    convert_srt_to_payload,
    convert_vtt_to_payload,
)
import requests
from django.db.models.functions import Concat
from django.db.models import Value
from django.http import HttpRequest
from transcript.views import export_transcript, get_transcript_id
from translation.views import export_translation, get_translation_id
from rest_framework.decorators import parser_classes
from rest_framework.parsers import MultiPartParser, FormParser
import regex


def get_export_translation(request, task_id, export_type):
    new_request = HttpRequest()
    new_request.method = "GET"
    new_request.user = request.user
    new_request.GET = request.GET.copy()
    new_request.GET["task_id"] = task_id
    new_request.GET["export_type"] = export_type
    return export_translation(new_request)


def get_export_transcript(request, task_id, export_type):
    new_request = HttpRequest()
    new_request.method = "GET"
    new_request.user = request.user
    new_request.GET = request.GET.copy()
    new_request.GET["task_id"] = task_id
    new_request.GET["export_type"] = export_type
    return export_transcript(new_request)


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

    def has_voice_over_edit_permission(self, user, videos):
        if user in videos[0].project_id.members.all() and (
            user.role == User.VOICEOVER_EDITOR
            or user.role == User.UNIVERSAL_EDITOR
            or user.role == User.VOICEOVER_REVIEWER
            or user.role == User.PROJECT_MANAGER
            or user.role == User.ORG_OWNER
            or user.role == User.ADMIN
            or user.is_superuser
        ):
            return True
        return False

    def has_voice_over_review_permission(self, user, videos):
        if user in videos[0].project_id.members.all() and (
            user.role == User.UNIVERSAL_EDITOR
            or user.role == User.VOICEOVER_REVIEWER
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
        for language in TRANSLATION_LANGUAGE_CHOICES:
            if target_language == language[0]:
                return language[1]
        return "-"

    def get_task_type_label(self, task_type):
        for t_type in TASK_TYPE:
            if task_type == t_type[0]:
                return t_type[1]

    def set_fail_for_translation_task(self, task):
        translation_task = (
            Task.objects.filter(target_language=task.target_language)
            .filter(task_type="TRANSLATION_EDIT")
            .filter(video=task.video)
            .first()
        )
        if translation_task is not None:
            translation_task.status = "FAILED"
            translation_task.save()

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

    def check_duplicate_tasks(
        self, request, task_type, target_language, user, videos, source_type
    ):
        duplicate_tasks = []
        duplicate_user_tasks = []
        delete_video = []
        same_language = []
        language_not_supported = []
        gender_not_supported = []
        original_src_translation = []

        for video in videos:
            task = Task.objects.filter(video=video)
            if target_language is not None:
                task = Task.objects.filter(video=video).filter(
                    target_language=target_language
                )
                if target_language == video.language:
                    same_language.append(video)
                if (
                    "VOICEOVER" in task_type
                    and target_language not in VOICEOVER_SUPPORTED_LANGUAGES.values()
                ):
                    language_not_supported.append(video)
                if (
                    "VOICEOVER" in task_type
                    and target_language == "brx"
                    and video.gender == "MALE"
                ):
                    gender_not_supported.append(video)

                if "TRANSLATION" in task_type and source_type == "ORIGINAL_SOURCE":
                    transcript_o = Transcript.objects.filter(video=video).first()
                    if transcript_o is not None:
                        original_src_translation.append(video)

            if (
                "TRANSCRIPTION" in task_type
                and Translation.objects.filter(video=video)
                .filter(translation_type="ORIGINAL_SOURCE")
                .first()
                is not None
            ):
                original_src_translation.append(video)
            if task.filter(task_type=task_type).first() is not None:
                duplicate_tasks.append(task.filter(task_type=task_type).first())

            if (
                task_type == "TRANSCRIPTION_REVIEW"
                and task.filter(task_type="TRANSLATION_EDIT").first() is not None
            ):
                delete_video.append(video)

            if (
                task_type == "TRANSLATION_REVIEW"
                and task.filter(task_type="VOICEOVER_EDIT").first() is not None
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

        return (
            duplicate_tasks,
            duplicate_user_tasks,
            delete_video,
            same_language,
            language_not_supported,
            gender_not_supported,
            original_src_translation,
        )

    def check_translation_exists(self, video, target_language):
        translation = Translation.objects.filter(video=video).filter(
            target_language=target_language
        )

        task_review = (
            Task.objects.filter(video=video)
            .filter(task_type="TRANSLATION_REVIEW")
            .filter(target_language=target_language)
            .first()
        )
        if translation.filter(status="TRANSLATION_REVIEW_COMPLETE").first() is not None:
            return translation.filter(status="TRANSLATION_REVIEW_COMPLETE").first()
        elif (
            translation.filter(status="TRANSLATION_EDIT_COMPLETE").first() is not None
            and task_review is None
        ):
            return translation.filter(status="TRANSLATION_EDIT_COMPLETE").first()
        else:
            return {
                "message": "Translation doesn't exist for this video.",
                "status": status.HTTP_400_BAD_REQUEST,
            }

    def check_transcript_exists(self, video):
        transcript = Transcript.objects.filter(video=video)

        task_review = (
            Task.objects.filter(video=video)
            .filter(task_type="TRANSCRIPTION_REVIEW")
            .first()
        )
        if (
            transcript.filter(status="TRANSCRIPTION_REVIEW_COMPLETE").first()
            is not None
        ):
            return transcript.filter(status="TRANSCRIPTION_REVIEW_COMPLETE").first()
        elif (
            transcript.filter(status="TRANSCRIPTION_EDIT_COMPLETE").first() is not None
            and task_review is None
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
            language_not_supported,
            gender_not_supported,
            original_src_translation,
        ) = self.check_duplicate_tasks(
            request, task_type, target_language, user_ids, videos, source_type
        )
        response = {}
        video_ids = []
        response_tasks = []
        consolidated_error = []
        detailed_error = []
        error_duplicate_tasks = []
        error_user_tasks = []
        error_same_language_tasks = []
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

        if len(same_language) > 0:
            for video in same_language:
                video_ids.append(video)
                error_same_language_tasks.append(
                    {"video": video, "task_type": task_type}
                )

        if len(delete_video) > 0:
            for video in delete_video:
                video_ids.append(video)
                error_review_tasks.append({"video": video, "task_type": task_type})

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
                        "target_language": self.get_target_language_label(
                            target_language
                        ),
                        "source_language": task["video"].get_language_label,
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
                        "source_language": task["video"].get_language_label,
                        "target_language": self.get_target_language_label(
                            target_language
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
                        "source_language": task["video"].get_language_label,
                        "target_language": self.get_target_language_label(
                            target_language
                        ),
                        "status": "Fail",
                        "message": "Task creation failed as selected task already exist.",
                    }
                )

        if len(error_review_tasks) > 0:
            consolidated_error.append(
                {
                    "message": "Task creation for Translation Review failed as Voice Over tasks already exists.",
                    "count": len(error_review_tasks),
                }
            )
            for task in error_review_tasks:
                detailed_error.append(
                    {
                        "video_name": task["video"].name,
                        "video_url": task["video"].url,
                        "task_type": self.get_task_type_label(task["task_type"]),
                        "source_language": task["video"].get_language_label,
                        "target_language": self.get_target_language_label(
                            target_language
                        ),
                        "status": "Fail",
                        "message": "Task creation for Translation Review failed as Voice Over task already exists.",
                    }
                )

        if len(original_src_translation) > 0:
            for video in original_src_translation:
                video_ids.append(video)
                detailed_error.append(
                    {
                        "video_name": video.name,
                        "video_url": video.url,
                        "task_type": self.get_task_type_label(task_type),
                        "source_language": video.get_language_label,
                        "target_language": self.get_target_language_label(
                            target_language
                        ),
                        "status": "Fail",
                        "message": "Task creation for Translation failed with source type Original Source as Transcription already exists.",
                    }
                )
            consolidated_error.append(
                {
                    "message": "Tasks creation for Translation failed with source type Original Source as Transcription already exists.",
                    "count": len(original_src_translation),
                }
            )

        for video in video_ids:
            videos.remove(video)
            if len(user_ids) > 0:
                del user_ids[-1]

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
                        user_id = self.assign_users(
                            task_type, video.project_id, video.language, target_language
                        )
                        if user_id is None:
                            user = request.user
                        else:
                            user = User.objects.get(pk=user_id)
                    else:
                        user = user_ids[0]

                    is_active = False
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
                            "target_language": task.get_target_language_label,
                            "source_language": task.get_src_language_label,
                            "status": "Successful",
                            "message": "Task is successfully created.",
                        }
                    )
                    transcript = self.check_transcript_exists(task.video)
                    if type(transcript) != dict:
                        if source_type == "MACHINE_GENERATED":
                            logging.info("Calling NMT API for %s", str(task.id))
                            celery_nmt_call.delay(task_id=task.id)
                            payloads = {source_type: ""}
                        else:
                            transcript = self.check_transcript_exists(task.video)
                            payloads = generate_translation_payload(
                                transcript, target_language, [source_type]
                            )
                            task.is_active = True
                            task.save()
                    else:
                        transcript = None
                        if source_type == "ORIGINAL_SOURCE":
                            payloads = generate_translation_payload(
                                transcript,
                                target_language,
                                [source_type],
                                task.video.url,
                            )
                            task.is_active = True
                            task.save()
                        else:
                            payloads = {source_type: ""}
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
                        user_id = self.assign_users(
                            task_type, video.project_id, video.language, target_language
                        )
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
                    if is_active:
                        send_mail_to_user(new_task)
                    tasks.append(new_task)

                new_translations = []
                for task in tasks:
                    detailed_error.append(
                        {
                            "video_name": task.video.name,
                            "video_url": task.video.url,
                            "task_type": self.get_task_type_label(task.task_type),
                            "target_language": task.get_target_language_label,
                            "source_language": task.get_src_language_label,
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

    def create_voiceover_task(
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
            language_not_supported,
            gender_not_supported,
            original_src_translation,
        ) = self.check_duplicate_tasks(
            request, task_type, target_language, user_ids, videos, source_type
        )
        response = {}
        video_ids = []
        response_tasks = []
        consolidated_error = []
        detailed_error = []
        error_duplicate_tasks = []
        error_user_tasks = []
        error_same_language_tasks = []
        error_language_not_supported_tasks = []
        error_gender_not_supported_tasks = []

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

        if len(language_not_supported) > 0:
            for video in language_not_supported:
                video_ids.append(video)
                error_language_not_supported_tasks.append(
                    {"video": video, "task_type": task_type}
                )

        if len(gender_not_supported) > 0:
            for video in gender_not_supported:
                video_ids.append(video)
                error_gender_not_supported_tasks.append(
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
                        "source_language": task["video"].get_language_label,
                        "target_language": self.get_target_language_label(
                            target_language
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
                        "source_language": task["video"].get_language_label,
                        "target_language": self.get_target_language_label(
                            target_language
                        ),
                        "status": "Fail",
                        "message": "Task creation failed as target language is same as source language.",
                    }
                )

        if len(error_language_not_supported_tasks):
            consolidated_error.append(
                {
                    "message": "Task creation failed as Target Langauge is not supported for VoiceOver.",
                    "count": len(error_language_not_supported_tasks),
                }
            )
            for task in error_language_not_supported_tasks:
                detailed_error.append(
                    {
                        "video_name": task["video"].name,
                        "video_url": task["video"].url,
                        "task_type": self.get_task_type_label(task["task_type"]),
                        "source_language": task["video"].get_language_label,
                        "target_language": self.get_target_language_label(
                            target_language
                        ),
                        "status": "Fail",
                        "message": "Task creation failed as Target Langauge is not supported for VoiceOver.",
                    }
                )

        if len(error_gender_not_supported_tasks):
            consolidated_error.append(
                {
                    "message": "Task creation failed as Male Voice is not supported for Bodo language.",
                    "count": len(error_language_not_supported_tasks),
                }
            )
            for task in error_gender_not_supported_tasks:
                detailed_error.append(
                    {
                        "video_name": task["video"].name,
                        "video_url": task["video"].url,
                        "task_type": self.get_task_type_label(task["task_type"]),
                        "source_language": task["video"].get_language_label,
                        "target_language": self.get_target_language_label(
                            target_language
                        ),
                        "status": "Fail",
                        "message": "Task creation failed as Male Voice is not supported for Bodo language.",
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
                        "source_language": task["video"].get_language_label,
                        "target_language": self.get_target_language_label(
                            target_language
                        ),
                        "status": "Fail",
                        "message": "Task creation failed as selected task already exist.",
                    }
                )

        if len(user_ids) > 0:
            if "EDIT" in task_type:
                permitted = self.has_voice_over_edit_permission(user_ids[0], videos)
            else:
                permitted = self.has_voice_over_review_permission(user_ids[0], videos)
        else:
            permitted = True

        if permitted:
            delete_tasks = []
            if "EDIT" in task_type:
                tasks = []
                for video in videos:
                    if len(user_ids) == 0:
                        user_id = self.assign_users(
                            task_type, video.project_id, video.language, target_language
                        )
                        if user_id is None:
                            user = request.user
                        else:
                            user = User.objects.get(pk=user_id)
                    else:
                        user = user_ids[0]
                    translation = self.check_translation_exists(video, target_language)

                    if type(translation) == dict:
                        translation = None

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
                        is_active=False,
                    )
                    new_task.save()
                    tasks.append(new_task)

                new_voiceovers = []
                tts_errors = 0
                for task in tasks:
                    if translation is None:
                        payloads = {"payload": {"completed_count": 0}}
                    else:
                        tts_payload = process_translation_payload(
                            translation, target_language
                        )
                        if (
                            type(tts_payload) == dict
                            and "message" in tts_payload.keys()
                        ):
                            message = tts_payload["message"]
                            tts_errors += 1
                            detailed_error.append(
                                {
                                    "video_name": task.video.name,
                                    "video_url": task.video.url,
                                    "task_type": self.get_task_type_label(
                                        task.task_type
                                    ),
                                    "target_language": task.get_target_language_label,
                                    "source_language": task.get_src_language_label,
                                    "status": "Fail",
                                    "message": message,
                                }
                            )
                            task.status = "FAILED"
                            task.save()
                            self.set_fail_for_translation_task(task)
                            video_ids.append(task.video)
                            delete_tasks.append(task)
                            consolidated_error.append(
                                {
                                    "message": message,
                                    "count": tts_errors,
                                }
                            )
                            logging.info("Error while calling TTS API")
                            continue
                        if source_type != "MANUALLY_CREATED":
                            (
                                tts_input,
                                target_language,
                                translation,
                                translation_id,
                                empty_sentences,
                            ) = tts_payload
                            logging.info("Async call for TTS")
                            celery_tts_call.delay(
                                task.id,
                                tts_input,
                                target_language,
                                translation,
                                translation_id,
                                empty_sentences,
                            )
                    if source_type == "MANUALLY_CREATED":
                        voiceover_obj = VoiceOver(
                            video=task.video,
                            user=task.user,
                            translation=translation,
                            payload={"payload": {"completed_count": 0}},
                            target_language=target_language,
                            task=task,
                            voice_over_type=source_type,
                            status="VOICEOVER_SELECT_SOURCE",
                        )
                        new_voiceovers.append(voiceover_obj)
                        if translation is not None:
                            task.is_active = True
                            task.save()
                            send_mail_to_user(task)
                    detailed_error.append(
                        {
                            "video_name": task.video.name,
                            "video_url": task.video.url,
                            "task_type": self.get_task_type_label(task.task_type),
                            "target_language": task.get_target_language_label,
                            "source_language": task.get_src_language_label,
                            "status": "Successful",
                            "message": "Task is successfully created.",
                        }
                    )
                if len(new_voiceovers) > 0:
                    voiceovers = VoiceOver.objects.bulk_create(new_voiceovers)
            else:
                tasks = []
                for video in videos:
                    if len(user_ids) == 0:
                        user_id = self.assign_users(
                            task_type, video.project_id, video.language, target_language
                        )
                        if user_id is None:
                            user = request.user
                        else:
                            user = User.objects.get(pk=user_id)
                    else:
                        user = user_ids[0]

                    voiceover = (
                        VoiceOver.objects.filter(video=video)
                        .filter(status="VOICEOVER_EDIT_COMPLETE")
                        .filter(target_language=target_language)
                        .first()
                    )
                    is_active = False
                    if voiceover is not None:
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
                    if is_active == True:
                        send_mail_to_user(new_task)
                    new_task.save()
                    tasks.append(new_task)

                new_voiceovers = []
                for task in tasks:
                    detailed_error.append(
                        {
                            "video_name": task.video.name,
                            "video_url": task.video.url,
                            "task_type": self.get_task_type_label(task.task_type),
                            "target_language": task.get_target_language_label,
                            "source_language": task.get_src_language_label,
                            "status": "Successful",
                            "message": "Task is successfully created.",
                        }
                    )
                    voiceover = (
                        VoiceOver.objects.filter(video=task.video)
                        .filter(status="VOICEOVER_EDIT_COMPLETE")
                        .filter(target_language=target_language)
                        .first()
                    )

                    if voiceover is not None:
                        payload = voiceover.payload
                        translation = voiceover.translation
                        is_active = True
                    else:
                        payload = {"payload": {}}
                        translation = None
                        is_active = False
                    voiceover_obj = VoiceOver(
                        video=task.video,
                        user=task.user,
                        translation=translation,
                        parent=voiceover,
                        payload=payload,
                        target_language=target_language,
                        task=new_task,
                        voice_over_type=source_type,
                        status="VOICEOVER_REVIEWER_ASSIGNED",
                    )
                    new_voiceovers.append(voiceover_obj)
                voiceovers = VoiceOver.objects.bulk_create(new_voiceovers)

            for task in delete_tasks:
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
                    "message": "The assigned user doesn't have permission to perform this task on voice overs in this project."
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
            language_not_supported,
            gender_not_supported,
            original_src_translation,
        ) = self.check_duplicate_tasks(
            request, task_type, None, user_ids, videos, source_type
        )

        response = {}
        video_ids = []
        response_tasks = []
        consolidated_error = []
        detailed_error = []
        error_duplicate_tasks = []
        error_user_tasks = []
        error_review_tasks = []
        error_original_src_trans = []
        target_language = "-"

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

        if len(original_src_translation) > 0:
            for video in original_src_translation:
                video_ids.append(video)
                detailed_error.append(
                    {
                        "video_name": video.name,
                        "video_url": video.url,
                        "task_type": task_type,
                        "source_language": video.get_language_label,
                        "target_language": self.get_target_language_label(
                            target_language
                        ),
                        "status": "Fail",
                        "message": "Tasks creation for Transcription failed as Translation exists with source type Original Source.",
                    }
                )
            consolidated_error.append(
                {
                    "message": "Tasks creation for Transcription failed as Translation exists with source type Original Source.",
                    "count": len(original_src_translation),
                }
            )

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
                        "source_language": task["video"].get_language_label,
                        "target_language": self.get_target_language_label(
                            target_language
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
                        "source_language": task["video"].get_language_label,
                        "target_language": self.get_target_language_label(
                            target_language
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
                        "source_language": task["video"].get_language_label,
                        "target_language": "-",
                        "status": "Fail",
                        "message": "Task creation for Transcription Review failed as Translation tasks already exists.",
                    }
                )

        for video in video_ids:
            videos.remove(video)
            if len(user_ids) > 0:
                del user_ids[-1]

        if len(user_ids) > 0:
            if "EDIT" in task_type:
                permitted = self.has_transcript_edit_permission(user_ids[0], videos)
            else:
                permitted = self.has_transcript_review_permission(user_ids[0], videos)
        else:
            permitted = True

        if permitted:
            delete_tasks = []
            if "EDIT" in task_type:
                logging.info("No error, creation started")
                tasks = []
                for video in videos:
                    if len(user_ids) == 0:
                        user_id = self.assign_users(
                            task_type,
                            video.project_id,
                            video.language,
                            target_language=None,
                        )
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
                        is_active=False,
                    )
                    new_task.save()
                    tasks.append(new_task)
                    logging.info("Task is created, and inactive")

                new_transcripts = []
                asr_errors = 0
                for task in tasks:
                    payloads = self.generate_transcript_payload(
                        task, [source_type], True
                    )
                    if source_type == "MACHINE_GENERATED":
                        detailed_error.append(
                            {
                                "video_name": task.video.name,
                                "video_url": task.video.url,
                                "task_type": self.get_task_type_label(task.task_type),
                                "target_language": task.get_target_language_label,
                                "source_language": task.get_src_language_label,
                                "status": "Successful",
                                "message": "Task is successfully created.",
                            }
                        )
                        continue
                    if type(payloads) != dict:
                        asr_errors += 1
                        detailed_error.append(
                            {
                                "video_name": task.video.name,
                                "video_url": task.video.url,
                                "task_type": self.get_task_type_label(task.task_type),
                                "target_language": task.get_target_language_label,
                                "source_language": task.get_src_language_label,
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
                        logging.info("Error while calling ASR API")
                        continue
                    detailed_error.append(
                        {
                            "video_name": task.video.name,
                            "video_url": task.video.url,
                            "task_type": self.get_task_type_label(task.task_type),
                            "target_language": task.get_target_language_label,
                            "source_language": task.get_src_language_label,
                            "status": "Successful",
                            "message": "Task is successfully created.",
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
                    if source_type != "MANUALLY_UPLOADED":
                        task.is_active = True
                        task.save()
                        logging.info(
                            "Transcript generated from ASR API and Task is active now."
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
                    logging.info("Fetched edited transcript for review task.")
                    is_active = False
                    if transcript is not None:
                        is_active = True

                    if len(user_ids) == 0:
                        user_id = self.assign_users(
                            task_type,
                            video.project_id,
                            video.language,
                            target_language=None,
                        )
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
                    if is_active == True:
                        send_mail_to_user(new_task)
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
                            "target_language": task.get_target_language_label,
                            "source_language": task.get_src_language_label,
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
                logging.info("Transcript Review tasks are created")
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
                logging.info(detailed_error[0]["message"])
                return Response(
                    {"message": detailed_error[0]["message"]},
                    status=status_code,
                )
            logging.info(message)
            return Response(
                {"message": message, "response": response},
                status=status.HTTP_207_MULTI_STATUS,
            )
        else:
            logging.info(
                "The assigned user doesn't have permission to perform this task on transcripts in this project."
            )
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
            start_time = datetime.datetime.strptime(vtt_line.start, "%H:%M:%S.%f")
            unix_start_time = datetime.datetime.timestamp(start_time)
            end_time = datetime.datetime.strptime(vtt_line.end, "%H:%M:%S.%f")
            unix_end_time = datetime.datetime.timestamp(end_time)

            sentences_list.append(
                {
                    "start_time": vtt_line.start,
                    "end_time": vtt_line.end,
                    "text": vtt_line.text,
                    "unix_start_time": unix_start_time,
                    "unix_end_time": unix_end_time,
                }
            )

        return json.loads(json.dumps({"payload": sentences_list}))

    def generate_transcript_payload(self, task, list_compare_sources, is_async=False):
        payloads = {}
        if "MACHINE_GENERATED" in list_compare_sources:
            if is_async == True:
                celery_asr_call.delay(task_id=task.id)
                payloads["MACHINE_GENERATED"] = {"payload": []}
            else:
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
            else:
                payloads["ORIGINAL_SOURCE"] = {"payload": []}

        if "MANUALLY_CREATED" in list_compare_sources:
            payloads["MANUALLY_CREATED"] = {"payload": []}
        if "MANUALLY_UPLOADED" in list_compare_sources:
            payloads["MANUALLY_UPLOADED"] = {"payload": []}
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
        tasks_deleted = []

        try:
            task = Task.objects.get(pk=pk)
        except Task.DoesNotExist:
            return Response(
                {"message": "Task not found"}, status=status.HTTP_404_NOT_FOUND
            )
        translation_tasks = set()
        flag = request.query_params.get("flag")
        if "flag" in kwargs:
            flag = kwargs["flag"]
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
                    for voiceover in (
                        Task.objects.filter(task_type="VOICEOVER_EDIT")
                        .filter(video=task.video)
                        .filter(target_language=translation.target_language)
                        .all()
                    ):
                        translation_tasks.add(voiceover)

            if len(translation_tasks) > 0:
                response = [
                    {
                        "task_type": translation_task.get_task_type_label,
                        "target_language": translation_task.get_target_language_label,
                        "video_name": translation_task.video.name,
                        "id": translation_task.id,
                        "video_id": translation_task.video.id,
                    }
                    for translation_task in translation_tasks
                ]

                if flag == "true" or flag == True:
                    for task_obj in translation_tasks:
                        tasks_deleted.append(task_obj.id)
                        task_obj.delete()
                    for task_obj in tasks_to_delete:
                        tasks_deleted.append(task_obj.id)
                        task_obj.delete()
                else:
                    return Response(
                        {
                            "response": response,
                            "message": "The Transcription task has dependent Translation/Voice Over tasks. Do you still want to delete all related translations as well?.",
                        },
                        status=status.HTTP_409_CONFLICT,
                    )
            else:
                for task_obj in tasks_to_delete:
                    tasks_deleted.append(task_obj.id)
                    task_obj.delete()

        if task.task_type in ["TRANSLATION_EDIT", "TRANSLATION_REVIEW"]:
            translations = (
                Translation.objects.filter(video=task.video)
                .filter(target_language=task.target_language)
                .all()
            )
            voice_over = (
                Task.objects.filter(video=task.video)
                .filter(target_language=task.target_language)
                .filter(task_type="VOICEOVER_EDIT")
                .all()
            )
            voiceover_tasks = [voiceover for voiceover in list(voice_over)]

            if "REVIEW" in task.task_type:
                translation_tasks = [task]
            else:
                translation_tasks = [
                    translation.task for translation in list(translations)
                ]

            if len(list(voiceover_tasks)) > 0:
                response = [
                    {
                        "task_type": voiceover_task.get_task_type_label,
                        "target_language": voiceover_task.get_target_language_label,
                        "video_name": voiceover_task.video.name,
                        "id": voiceover_task.id,
                        "video_id": voiceover_task.video.id,
                    }
                    for voiceover_task in voiceover_tasks
                ]

                if flag == "true" or flag == True:
                    for task_obj in voiceover_tasks + translation_tasks:
                        tasks_deleted.append(task_obj.id)
                        task_obj.delete()
                else:
                    return Response(
                        {
                            "response": response,
                            "message": "The Translation task has dependent Voice Over tasks. Do you still want to delete all related Voice Over as well?.",
                        },
                        status=status.HTTP_409_CONFLICT,
                    )
            else:
                for task_obj in translation_tasks:
                    tasks_deleted.append(task_obj.id)
                    task_obj.delete()

        if task.task_type == "VOICEOVER_EDIT":
            tasks_deleted.append(task.id)
            task.delete()

        return Response(
            {
                "tasks_deleted": list(set(tasks_deleted)),
                "message": "Task is deleted, with all associated Transcripts/Translations/Voice Over",
            },
            status=status.HTTP_200_OK,
        )

    @swagger_auto_schema(
        method="get",
        manual_parameters=[
            openapi.Parameter(
                "task_ids",
                openapi.IN_QUERY,
                description=("A list to pass the task ids"),
                type=openapi.TYPE_ARRAY,
                items=openapi.Items(type=openapi.TYPE_INTEGER, format="ids"),
                required=True,
            ),
            openapi.Parameter(
                "export_type",
                openapi.IN_QUERY,
                description=("export type parameter srt/vtt/txt/docx"),
                type=openapi.TYPE_STRING,
                required=True,
            ),
        ],
        responses={200: "Task is exported"},
    )
    @action(detail=False, methods=["get"], url_path="download_tasks")
    def download_tasks(self, request):
        """
        API Endpoint to download all the completed transcripts/translations for a video
        Endpoint: /video/download_all/
        Method: GET
        """
        task_ids = request.query_params.get("task_ids")
        export_type = request.query_params.get("export_type")
        if task_ids is None or export_type is None:
            return Response(
                {"message": "missing required params: video_id or export_type"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        valid_tasks = []
        invalid_tasks = []

        for task_id in task_ids.split(","):
            task = Task.objects.filter(pk=int(task_id)).first()
            if task is None:
                invalid_tasks.append(task_id)
            else:
                valid_tasks.append(task)

        zip_file = io.BytesIO()
        non_completed_tasks = 0
        time_now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with zipfile.ZipFile(zip_file, "w") as zf:
            for task in valid_tasks:
                if "COMPLETE" in task.status:
                    if "TRANSCRIPT" in task.task_type:
                        transcript = get_export_transcript(
                            request, task.id, export_type
                        )
                        if "docx" in export_type:
                            content = b"".join(transcript.streaming_content)
                        else:
                            content = transcript.content
                        if task.video.project_id.organization_id.id == 16 and len(task.description) > 0:
                            file_name = f"{task.description}.{export_type}"
                        else:
                            file_name = f"{task.video.name}_{time_now}.{export_type}"
                        zf.writestr(
                            file_name, content
                        )
                    elif "TRANSLATION" in task.task_type:
                        translation = get_export_translation(
                            request, task.id, export_type
                        )
                        if "docx" in export_type:
                            content = b"".join(translation.streaming_content)
                        else:
                            content = translation.content
                        if task.video.project_id.organization_id.id == 16 and len(task.description) > 0:
                            file_name = f"{task.description}.{export_type}"
                        else:
                            file_name = f"{task.video.name}_{time_now}.{export_type}"
                        zf.writestr(
                            f"{task.video.name}_{time_now}_{task.target_language}.{export_type}",
                            content,
                        )
                    else:
                        logging.info("Not a valid task type")
                else:
                    non_completed_tasks += 1

        if non_completed_tasks == len(valid_tasks):
            return Response(
                {
                    "message": "The selected task(s) doesn't have completed transcripts/translations."
                },
                status=status.HTTP_404_NOT_FOUND,
            )
        zip_file.seek(0)
        response = HttpResponse(
            zip_file, content_type="application/zip", status=status.HTTP_200_OK
        )
        response[
            "Content-Disposition"
        ] = f"attachment; filename=Chitralekha_{time_now}_all.zip"
        return response

    @swagger_auto_schema(
        method="delete",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=["task_ids"],
            properties={
                "task_ids": openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    description="A string to pass the transcript data",
                ),
                "flag": openapi.Schema(
                    type=openapi.TYPE_BOOLEAN,
                    description="A boolean to complete the task",
                ),
            },
            description="Post request body for projects which have save_type == new_record",
        ),
        responses={
            200: "Transcript has been saved successfully",
        },
    )
    @action(detail=False, methods=["delete"], url_path="delete_bulk_tasks")
    def delete_bulk_tasks(self, request, *args, **kwargs):
        task_ids = request.data.get("task_ids")
        flag = request.data.get("flag")
        if flag == None:
            flag = False

        tasks = []
        detailed_report = []
        error_report = []
        tasks_to_delete = set()
        videos = set()
        deleted_tasks = []
        for task_id in task_ids:
            try:
                task_obj = Task.objects.get(pk=task_id)
            except Task.DoesNotExist:
                if task_id in deleted_tasks:
                    continue
                return Response(
                    {"message": "Task not found"}, status=status.HTTP_404_NOT_FOUND
                )

            delete = self.delete_task(request, pk=task_id, flag=flag)
            if delete.status_code == 200:
                deletion_status = "Success"
                detailed_report.append(
                    {
                        "video_name": task_obj.video.name,
                        "video_id": task_obj.video_id,
                        "task_type": task_obj.task_type,
                        "target_language": task_obj.target_language,
                    }
                )
                deleted_tasks.extend(delete.data.get("tasks_deleted"))
            elif delete.status_code == 409:
                dependent_tasks = delete.data
                for task in dependent_tasks["response"]:
                    error_report.append(
                        {
                            "video_name": task["video_name"],
                            "video_id": task["video_id"],
                            "task_type": task["task_type"],
                            "target_language": task["target_language"],
                        }
                    )
                    videos.add(task["video_id"])
                    tasks_to_delete.add(task_obj.id)
            else:
                deletion_status = "Fail"
                detailed_report.append(
                    {
                        "video_name": task.video.name,
                        "video_id": task.video_id,
                        "task_type": task.task_type,
                        "target_language": task["target_language"],
                    }
                )

        response = {}
        if len(error_report) > 0:
            response["error_report"] = error_report
            response["task_ids"] = list(tasks_to_delete)
            if len(list(videos)) > 1:
                response[
                    "message"
                ] = "The Transcription task for video_id(s) {0} has dependent translation tasks. Do you still want to delete all related translations as well?.".format(
                    str(list(videos))
                )
            else:
                response[
                    "message"
                ] = "The Transcription task has dependent translation tasks. Do you still want to delete all related translations as well?."
            return Response(
                response,
                status=status.HTTP_409_CONFLICT,
            )
        return Response(
            {
                "message": "Task(s) deleted, with all associated transcripts/translations"
            },
            status=status.HTTP_200_OK,
        )

    def assign_users(self, task_type, project, video_language, target_language=None):
        videos = Video.objects.filter(project_id=project)
        roles = allowed_roles[task_type]
        users = (
            User.objects.filter(id__in=project.members.all())
            .filter(
                Q(has_accepted_invite=True)
                & Q(role__in=roles)
                & Q(
                    languages__contains=[
                        dict(TRANSLATION_LANGUAGE_CHOICES)[video_language]
                    ]
                )
            )
            .values_list("id", flat=True)
        )
        if (
            task_type
            in (
                "TRANSLATION_EDIT",
                "TRANSLATION_REVIEW",
                "VOICEOVER_EDIT",
                "VOICEOVER_REVIEW",
            )
            and target_language
        ):
            users = users.filter(
                Q(
                    languages__contains=[
                        dict(TRANSLATION_LANGUAGE_CHOICES)[target_language]
                    ]
                )  # filtering of users based on target language
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

        if "TRANSLATION" in task_type or "VOICEOVER" in task_type:
            target_language = request.data.get("target_language")
            if target_language is None:
                logging.info("Target language is missing")
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

                if description is None:
                    description = video.description

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
        elif "VOICEOVER" in task_type:
            source_type = (
                project.default_voiceover_type or organization.default_voiceover_type
            )
            if source_type is None:
                source_type = backend_default_voice_over_type
            return self.create_voiceover_task(
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
        is_active = request.data.get("is_active")

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
            elif task.task_type == "VOICEOVER_EDIT":
                permission = self.has_voice_over_edit_permission(user_obj, [task.video])
            else:
                logging.info("Not a Valid Type")

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

        if is_active is not None:
            task.is_active = True
        task.save()
        return Response(
            {"message": "Task is successfully updated."},
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=["patch"], url_path="update_multiple_tasks")
    def update_multiple_tasks(self, request, *args, **kwargs):
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
                    logging.info("Not a Valid Type")

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
            {"value": "VOICEOVER", "label": "Voice Over"},
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
            {"id": 5, "value": "VOICEOVER_EDIT", "label": "VoiceOver Edit"},
        ]
        return Response(response, status=status.HTTP_200_OK)

    @action(detail=False, methods=["get"], url_path="get_supported_bulk_task_types")
    def get_supported_bulk_task_types(self, request):
        """
        Fetches all task types.
        """
        response = [
            {"id": 1, "value": "TRANSCRIPTION_REVIEW", "label": "Transcription Review"},
            {"id": 2, "value": "TRANSLATION_EDIT", "label": "Translation Edit"},
            {"id": 3, "value": "TRANSLATION_REVIEW", "label": "Translation Review"},
            {"id": 4, "value": "VOICEOVER_EDIT", "label": "VoiceOver Edit"},
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
        elif type == "VOICEOVER":
            target_language = request.query_params.get("target_language")
            label = "VoiceOver"
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
        elif type == "VOICEOVER":
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

    @swagger_auto_schema(
        method="get",
        manual_parameters=[
            openapi.Parameter(
                "queue",
                openapi.IN_QUERY,
                description=("The type of queue to inspect"),
                type=openapi.TYPE_STRING,
                required=True,
            ),
        ],
        responses={200: "successful", 500: "unable to query celery"},
    )
    @action(detail=False, methods=["get"], url_path="inspect_queue")
    def inspect_queue(self, request):
        queue=request.query_params.get("queue")

        if queue=='nmt':
            queue_type="celery@nmt_worker"
        elif queue=='tts':
            queue_type="celery@asr_tts_worker"
        else:
            queue_type="celery@asr_tts_worker"

        try:
            task_list = []
            url = f"{flower_url}/api/tasks"
            params = {
                "state": "STARTED",
                "sort_by": "received",
                "workername": queue_type,
            }
            if flower_username and flower_password:
                res = requests.get(
                    url, params=params, auth=(flower_username, flower_password)
                )
            else:
                res = requests.get(url, params=params)
            data = res.json()
            task_data = list(data.values())
            for elem in task_data:
                if queue == "asr" and elem["name"] == "task.tasks.celery_asr_call":
                    task_list.append(eval(elem["kwargs"])["task_id"])
                elif queue == "tts" and elem["name"] == "task.tasks.celery_tts_call":
                    # task_list.append(eval(elem["kwargs"])["task_id"])
                    task_list.append(eval(elem['args'].split(',')[0].split('(')[1]))
                elif queue == "nmt" and elem["name"] == "task.tasks.celery_nmt_call":
                    task_list.append(eval(elem["kwargs"])["task_id"])
                else:
                    pass
            params = {
                "state": "RECEIVED",
                "sort_by": "received",
                "workername": queue_type,
            }
            if flower_username and flower_password:
                res = requests.get(
                    url, params=params, auth=(flower_username, flower_password)
                )
            else:
                res = requests.get(url, params=params)
            data = res.json()
            task_data = list(data.values())
            for elem in task_data:
                if queue == "asr" and elem["name"] == "task.tasks.celery_asr_call":
                    task_list.append(eval(elem["kwargs"])["task_id"])
                elif queue == "tts" and elem["name"] == "task.tasks.celery_tts_call":
                    # task_list.append(eval(elem["kwargs"])["task_id"])
                    task_list.append(eval(elem['args'].split(',')[0].split('(')[1]))
                elif queue == "nmt" and elem["name"] == "task.tasks.celery_nmt_call":
                    task_list.append(eval(elem["kwargs"])["task_id"])
                else:
                    pass
            if task_list:
                task_details = Task.objects.filter(id__in=task_list).values(
                    "id",
                    "video__duration",
                    "video__id",
                    "created_by__organization__title",
                    submitter_name=Concat(
                        "created_by__first_name", Value(" "), "created_by__last_name"
                    ),
                )
                for elem in task_details:
                    task_dict = {
                        "task_id": elem["id"],
                        "video_id": elem["video__id"],
                        "submitter_name": elem["submitter_name"],
                        "org_name": elem["created_by__organization__title"],
                        "video_duration": str(elem["video__duration"]),
                    }
                    i = task_list.index(elem["id"])
                    task_list[i] = task_dict

            return Response(
                {"message": "successful", "data": task_list}, status=status.HTTP_200_OK
            )
        except Exception:
            return Response(
                {"message": "Unable to query celery", "data": []},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @swagger_auto_schema(
        method="patch",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=["time_spent"],
            properties={
                "time_spent": openapi.Schema(
                    type=openapi.TYPE_INTEGER,
                    description="time spent",
                ),
            },
            description="Post request body for updating time spent.",
        ),
        responses={
            200: "Updated time spent on task.",
        },
    )
    @action(
        detail=True,
        methods=["PATCH"],
        name="Update Time Spent",
        url_name="update_time_spent",
    )
    def update_time_spent(self, request, pk=None):
        try:
            task = Task.objects.get(pk=pk)
        except Task.DoesNotExist:
            return Response(
                {"message": "Task does not exist"},
                status=status.HTTP_404_NOT_FOUND,
            )
        time_spent = request.data.get("time_spent", 0)
        if task.time_spent == None:
            task.time_spent = time_spent
        else:
            task.time_spent += time_spent
        task.save()
        return Response(
            {"message": "Time spent on task updated successfully."},
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["get"], url_path="get_fail_info")
    def get_fail_info(self, request, pk, *args, **kwargs):
        try:
            task = Task.objects.get(pk=pk)
        except Task.DoesNotExist:
            return Response(
                {"message": "Task not found"}, status=status.HTTP_404_NOT_FOUND
            )

        bad_sentences = []
        if "TRANSLATION" in task.task_type:
            translation = get_translation_id(task)
            if translation:
                if "COMPLETE" not in translation.status:
                    bad_sentences = get_bad_sentences_in_progress(
                        translation, task.target_language
                    )
                else:
                    bad_sentences = get_bad_sentences(translation, task.target_language)
                if len(bad_sentences) > 0:
                    return Response(
                        {
                            "data": bad_sentences,
                            "message": "Sentences with issues are returned.",
                        },
                        status=status.HTTP_200_OK,
                    )
                else:
                    return Response(
                        {"message": "There is no issue in sentences."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
        elif "TRANSCRIPTION" in task.task_type:
            transcript = get_transcript_id(task)
            bad_sentences = get_bad_sentences_in_progress(transcript, "")
            if len(bad_sentences) > 0:
                return Response(
                    {
                        "data": bad_sentences,
                        "message": "Sentences with issues are returned.",
                    },
                    status=status.HTTP_200_OK,
                )
            else:
                return Response(
                    {"message": "There is no issue in sentences."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        else:
            return Response(
                {"message": "There is no issue in sentences."},
                status=status.HTTP_400_BAD_REQUEST,
            )

    @is_project_owner
    @swagger_auto_schema(
        method="post",
        manual_parameters=[
            openapi.Parameter(
                "delete_voiceover_and_reopen",
                openapi.IN_QUERY,
                description=("Delete dependent voiceover and reopen('true'/'false')"),
                type=openapi.TYPE_STRING,
                required=False,
            ),
        ],
    )
    @action(detail=True, methods=["post"], url_path="reopen_translation_task")
    def reopen_translation_task(self, request, pk, *args, **kwargs):
        delete_voiceover_and_reopen=request.query_params.get("delete_voiceover_and_reopen")
        if delete_voiceover_and_reopen=='true':
            delete_voiceover_and_reopen=True
        else:
            delete_voiceover_and_reopen=False
        
        try:
            task = Task.objects.get(pk=pk)
        except Task.DoesNotExist:
            return Response(
                {"message": "Task not found"}, status=status.HTTP_404_NOT_FOUND
            )
        if task.status == "FAILED" and "TRANSLATION" in task.task_type:
            if "TRANSLATION_REVIEW" in task.task_type:
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
                    .all()
                )
            else:
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
                    .all()
                )
            if (
                translation_inprogress_obj is not None
                and translation_completed_obj is not None
            ):
                translation_completed_obj.parent = None
                translation_completed_obj.save()
                translation_inprogress_obj.delete()
                translation_completed_obj.status = "TRANSLATION_REVIEW_INPROGRESS" if "TRANSLATION_REVIEW" in task.task_type else "TRANSLATION_EDIT_INPROGRESS"
                translation_completed_obj.save()
                task.status = "REOPEN"
                task.save()
            else:
                return Response(
                    {"message": "Can not reopen this task."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        if task.status == "COMPLETE" and "TRANSLATION" in task.task_type:
            translation_review_task=(
                Task.objects.filter(video=task.video)
                .filter(target_language=task.target_language)
                .filter(task_type="TRANSLATION_REVIEW")
                .first()
            )
            if (
                "TRANSLATION_EDIT" in task.task_type
                and translation_review_task is not None
                and translation_review_task.is_active==True
            ):
                return Response(
                    {"message": "Can not reopen this task. Corrosponding Translation Review task is active"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
                
            voiceover_task = (
                Task.objects.filter(video=task.video)
                .filter(target_language=task.target_language)
                .filter(task_type="VOICEOVER_EDIT")
                .first()
            )
            if voiceover_task is not None:
                if delete_voiceover_and_reopen==False:
                    response = [
                        {
                            "task_type": voiceover_task.get_task_type_label,
                            "target_language": voiceover_task.get_target_language_label,
                            "video_name": voiceover_task.video.name,
                            "id": voiceover_task.id,
                            "video_id": voiceover_task.video.id,
                        }
                    ]
                    return Response(
                        {
                            "response": response,
                            "message": "Can't reopen the Translation task as there is a dependent VoiceOver task.",
                        },
                        status=status.HTTP_409_CONFLICT,
                    )
                else:
                    if "TRANSLATION_REVIEW" in task.task_type:
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
                            .all()
                        )

                    else:
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
                            .all()
                        )
                    voice_over_selected_source_obj = (
                            VoiceOver.objects.filter(status="VOICEOVER_SELECT_SOURCE")
                            .filter(video=task.video)
                            .filter(target_language=task.target_language)
                            .first()
                        )
                    voice_over_inprogress_obj = (
                            VoiceOver.objects.filter(status="VOICEOVER_EDIT_INPROGRESS")
                            .filter(video=task.video)
                            .filter(target_language=task.target_language)
                            .first()
                        )
                    
                    if (
                        translation_inprogress_obj is not None
                        and translation_completed_obj is not None
                        and voice_over_selected_source_obj is not None
                        and voice_over_inprogress_obj is None
                    ):
                        translation_completed_obj.parent = None
                        translation_completed_obj.save()
                        translation_inprogress_obj.delete()
                        translation_completed_obj.status = "TRANSLATION_REVIEW_INPROGRESS" if "TRANSLATION_REVIEW" in task.task_type else "TRANSLATION_EDIT_INPROGRESS"
                        translation_completed_obj.save()
                        task.status = "REOPEN"
                        task.save()
                        
                        voice_over_selected_source_obj.delete()
                        voiceover_task.is_active = False
                        voiceover_task.save()

                    
                    else:
                        return Response(
                            {"message": "Can not reopen this task."},
                            status=status.HTTP_400_BAD_REQUEST,
                        )
            else:
                if "TRANSLATION_REVIEW" in task.task_type:
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
                        .all()
                    )
                else:
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
                        .all()
                    )

                if (
                    translation_inprogress_obj is not None
                    and translation_completed_obj is not None
                ):
                    translation_completed_obj.parent = None
                    translation_completed_obj.save()
                    translation_inprogress_obj.delete()
                    translation_completed_obj.status = "TRANSLATION_REVIEW_INPROGRESS" if "TRANSLATION_REVIEW" in task.task_type else "TRANSLATION_EDIT_INPROGRESS"
                    translation_completed_obj.save()
                    task.status = "REOPEN"
                    task.save()
                else:
                    return Response(
                        {"message": "Can not reopen this task."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
        else:
            return Response(
                {"message": "Can not reopen this task."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response({"message": "Task is reopened."}, status=status.HTTP_200_OK)

    @swagger_auto_schema(
        method="post",
        manual_parameters=[
            openapi.Parameter(
                "project_id",
                openapi.IN_QUERY,
                description=("An integer to identify the project"),
                type=openapi.TYPE_INTEGER,
                required=True,
            ),
        ],
        responses={
            200: "Word count populated successfully",
            400: "Error in populating word count",
        },
    )
    @action(
        detail=False,
        methods=["post"],
        url_path="populate_word_count",
        url_name="populate_word_count",
    )
    def populate_word_count(self, request):
        """
        Adding word count for existing translations and transcriptions
        """
        project_id = request.query_params.get("project_id")
        translations = Translation.objects.filter(Q(video__project_id=project_id)
            & Q(status__in=["TRANSLATION_EDIT_COMPLETE", "TRANSLATION_REVIEW_COMPLETE"]))
        for translation_obj in translations:
            try:
                if (
                    translation_obj.payload != ""
                    and translation_obj.payload is not None
                ):
                    num_words = 0
                    for idv_translation in translation_obj.payload["payload"]:
                        if "target_text" in idv_translation.keys():
                            cleaned_text = regex.sub(
                                r"[^\p{L}\s]", "", idv_translation["target_text"]
                            ).lower()  # for removing special characters
                            cleaned_text = regex.sub(
                                r"\s+", " ", cleaned_text
                            )  # for removing multiple blank spaces
                            num_words += len(cleaned_text.split(" "))
                    translation_obj.payload["word_count"] = num_words
                    translation_obj.save()
                else:
                    translation_obj.payload = {"payload": [], "word_count": 0}
                    translation_obj.save()
            except:
                return Response(
                    {
                        "message": "Error in populating word count for translation object."
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

        transcripts = Transcript.objects.filter(Q(video__project_id=project_id) 
            & Q(status__in=["TRANSCRIPTION_EDIT_COMPLETE", "TRANSCRIPTION_REVIEW_COMPLETE"]))
        for transcript_obj in transcripts:
            try:
                if (
                    transcript_obj.payload != "" 
                    and transcript_obj.payload is not None
                ):
                    num_words = 0
                    for idv_transcription in transcript_obj.payload["payload"]:
                        if "text" in idv_transcription.keys():
                            cleaned_text = regex.sub(
                                r"[^\p{L}\s]", "", idv_transcription["text"]
                            ).lower()  # for removing special characters
                            cleaned_text = regex.sub(
                                r"\s+", " ", cleaned_text
                            )  # for removing multiple blank spaces
                            num_words += len(cleaned_text.split(" "))
                    transcript_obj.payload["word_count"] = num_words
                    transcript_obj.save()
                else:
                    transcript_obj.payload = {"payload": [], "word_count": 0}
                    transcript_obj.save()
            except:
                return Response(
                    {
                        "message": "Error in populating word count for transcript object."
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

        return Response(
            {
                "message": "Successfully populated word count for transcript and translation objects."
            },
            status=status.HTTP_200_OK,
        )


@swagger_auto_schema(
    method="post",
    manual_parameters=[
        openapi.Parameter(
            name="subtitles",
            in_=openapi.IN_FORM,
            type=openapi.TYPE_FILE,
            required=True,
            description="SRT/VTT File to upload",
        ),
    ],
    responses={200: "Subtitles imported successfully"},
)
@api_view(["POST"])
@parser_classes([MultiPartParser, FormParser])
def import_subtitles(request, pk=None):
    task = Task.objects.get(pk=pk)
    logging.info(request)
    logging.info(request.user)
    logging.info(request.user.email)
    logging.info(task.user.email)
    if request.user.email != task.user.email:
        return Response(
            {
                "message": "You are not allowed to import subtitle. Only task assignee can import it."
            },
            status=status.HTTP_403_FORBIDDEN,
        )
    subtitles = request.data.get("subtitles")
    if subtitles is None:
        return Response(
            {"message": "Subtitles not found"}, status=status.HTTP_404_NOT_FOUND
        )
    if request.FILES["subtitles"].name.split(".")[-1] not in ["srt", "vtt"]:
        logging.info(subtitles.content_type)
        return Response(
            {"message": "Invalid file format"}, status=status.HTTP_400_BAD_REQUEST
        )
    if request.FILES["subtitles"].name.endswith("vtt"):
        subtitles = subtitles.read().decode("utf-8")
        try:
            subtitles = convert_vtt_to_payload(subtitles)
        except Exception as e:
            logging.info(e)
            return Response(
                {"message": "Invalid file format"}, status=status.HTTP_400_BAD_REQUEST
            )
    else:
        subtitles = subtitles.read().decode("utf-8")
        try:
            subtitles = convert_srt_to_payload(subtitles)
        except Exception as e:
            return Response(
                {"message": "Invalid file format"}, status=status.HTTP_400_BAD_REQUEST
            )
    if task.task_type == TRANSCRIPTION_EDIT:
        transcript_obj = (
            Transcript.objects.filter(video=task.video)
            .filter(status=TRANSCRIPTION_SELECT_SOURCE)
            .first()
        )
        if transcript_obj is not None:
            transcript_obj.payload = subtitles
            transcript_obj.save()
        else:
            Transcript.objects.create(
                transcript_type=MANUALLY_UPLOADED,
                video=task.video,
                language=task.video.language,
                user=request.user,
                task=task,
                status=TRANSCRIPTION_SELECT_SOURCE,
                payload=subtitles,
            )
    else:
        return Response(
            {"message": "Invalid task type"}, status=status.HTTP_400_BAD_REQUEST
        )
    task.is_active = True
    task.save()
    return Response(
        {"message": "Subtitles imported successfully"}, status=status.HTTP_200_OK
    )
