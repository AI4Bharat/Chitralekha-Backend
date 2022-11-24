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
from video.utils import get_subtitles_from_google_video
from rest_framework.permissions import IsAuthenticated

from .models import (
    Task,
    TRANSCRIPTION_SELECT_SOURCE,
    TRANSCRIPTION_EDIT,
    TRANSCRIPTION_REVIEW,
    TRANSLATION_SELECT_SOURCE,
    TRANSLATION_EDIT,
    TRANSLATION_REVIEW,
    NEW,
    INPROGRESS,
    COMPLETE,
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
        if (user in video.project_id.members.all() and (
            user.role == User.TRANSCRIPT_EDITOR
            or user.role == User.UNIVERSAL_EDITOR
            or user.role == User.TRANSCRIPT_REVIEWER
            or user.role == User.PROJECT_MANGAGER
            or user.role == User.ORG_OWNER
            or user.is_superuser)):
            return True
        return Response(
            {"message": "The assigned user doesn't have permission to edit transcripts in this project."},
            status=status.HTTP_400_BAD_REQUEST,
        )


    def has_transcript_review_permission(self, user, video):
        if (user in video.project_id.members.all() and (
            user.role == User.UNIVERSAL_EDITOR
            or user.role == User.TRANSCRIPT_REVIEWER
            or user.role == User.PROJECT_MANGAGER
            or user.role == User.ORG_OWNER
            or user.is_superuser)):
            return True
        return Response(
            {"message": "The assigned user doesn't have permission to review transcripts in this project."},
            status=status.HTTP_400_BAD_REQUEST,
        )


    def has_translate_edit_permission(self, user, video):
        if (user in video.project_id.members.all() and (
            user.role == User.UNIVERSAL_EDITOR
            or user.role == User.TRANSLATION_EDITOR
            or user.role == User.TRANSLATION_REVIEWER
            or user.role == User.PROJECT_MANGAGER
            or user.role == User.ORG_OWNER
            or user.is_superuser)):
            return True
        return Response(
            {"message": "The assigned user doesn't have permission to edit translations in this project."},
            status=status.HTTP_400_BAD_REQUEST,
        )


    def has_translate_review_permission(self, user, video):
        if (user in video.project_id.members.all() and (
            user.role == User.UNIVERSAL_EDITOR
            or user.role == User.TRANSLATION_REVIEWER
            or user.role == User.PROJECT_MANGAGER
            or user.role == User.ORG_OWNER
            or user.is_superuser)):
            return True
        return Response(
            {"message": "The assigned user doesn't have permission to edit translations in this project."},
            status=status.HTTP_400_BAD_REQUEST,
        )


    def generate_translation(self, video, lang, transcript, user, translation_type, task, payload):
        status = "TRANSLATION_SELECT_SOURCE"
        translate_obj = Translation(
            video=video,
            user=user,
            transctipt=transcript,
            payload=payload,
            target_language=lang,
            task=task,
            translation_type=translation_type,
            status=status,
        )
        translate_obj.save()
        return {"translate_id": translate_obj.id, "data": translate_obj.payload}


    def check_duplicate_task(self, task_type, task, user):
        if task.filter(task_type=task_type).first() is not None:
            return {
                "message": "Task is already created.",
                "status": status.HTTP_400_BAD_REQUEST
                }

        if "TRANSLATION" in task_type:
            transcript_task_type = "TRANSCRIPTION_EDIT_COMPLETE"
            if task.filter(task_type=transcript_task_type).first() is None:
                return {
                    "message": "Creation of Translation task is not permissible until Transcription is not done.",
                    "status": status.HTTP_400_BAD_REQUEST
                    }
        if "EDIT" in task_type:
            source_task_type = task_type.split('_')[0] + '_' + "SELECT_SOURCE"
            if task.filter(task_type=source_task_type).first() is None:
                return {
                    "message": "Creation of Edit task is not permissible until selection of source is not done.",
                    "status": status.HTTP_400_BAD_REQUEST
                    }
        if "REVIEW" in task_type:
            edit_task_type = task_type.split('_')[0] + '_' + "EDIT"
            if task.filter(task_type=edit_task_type).filter(status="COMPLETE").first() is None:
                return {
                    "message": "Creation of Review task is not permissible until Editing is not completed.",
                    "status": status.HTTP_400_BAD_REQUEST
                    }
            if task.filter(task_type=task_type).filter(user=user).first():
                if not (request.user.role > 4 or request.user.is_superuser):
                    return {
                        "message": "Same user can't be Editor and Reviewer of a video.",
                        "status" :status.HTTP_400_BAD_REQUEST
                        }
        return {}


    def check_transcript_exists(self, video, verified_transcript):
        transcript = Transcript.objects.filter(video=video)

        if verified_transcript:
            if transcript.filter(status="TRANSCRIPTION_EDIT_COMPLETE").first() is None:
                return Response(
                    {"message": "Transcript doesn't exist for this video."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            else:
                return transcript.filter(status="TRANSCRIPTION_EDIT_COMPLETE").first()
        else:
            if transcript.filter(status="TRANSCRIPTION_REVIEW_COMPLETE").first() is None:
                return Response(
                    {"message": "Reviewed Transcript doesn't exist for this video."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            else:
                return transcript.filter(status="TRANSCRIPTION_REVIEW_COMPLETE").first()


    def create_translation_task(self, video, user, target_language, task_type, request, verified_transcript):
        task = (Task.objects.filter(video=video).
            filter(target_language=target_language))

        response = check_duplicate_task(task_type, task, user)
        if len(response) > 0:
            return Response(
                {"message": response["message"]},
                status=response["status"]
                )

        transcript_obj = check_transcript_exists(video, verified_transcript)
        if "EDIT" in task_type:
            permitted = has_translate_edit_permission(user, video)
        else:
            permitted = has_translate_review_permission(user, video)

        if permitted:
                new_task = Task(
                                task_type=task_type,
                                video=video,
                                target_language=target_language,
                                user=user,
                                created_by=request.user,
                                status="NEW"
                            )
                new_task.save()


                if "EDIT" in task_type:
                    # response = generate_translation(batch_size, transcript_id, target_language, user=user, task=new_task)
                    translation = (Translation.objects.filter(video=video)
                                      .filter(target_language=target_language)
                                      .filter(status="TRANSLATION_SELECT_SOURCE")
                                      .first())

                    if translation is not None:
                        translate_obj = Translation(
                            video=video,
                            user=user,
                            transctipt=transcript,
                            parent=translation,
                            payload=translation.payload,
                            target_language=lang,
                            task=new_task,
                            translation_type=translation.translation_type,
                            status="TRANSLATION_EDITOR_ASSIGNED"
                        )
                        translation_obj.save()
                        response = {"task_id": new_task.id,
                                    "translation_id": translate_obj.id,
                                    "data": translate_obj.payload}
                else:
                    edit_task_type = task_type.split('_')[0] + '_' + "EDIT"
                    translation = (Translation.objects.filter(video=video)
                                                   .filter(translation_type=edit_task_type)
                                                   .filter(status="TRANSLATION_EDIT_COMPLETE")
                                                   .first())
                    if translation is None:
                        return Response(
                            {"message": "Translation review task can't be created, as editing is not done yet."},
                            status=status.HTTP_400_BAD_REQUEST,
                        )
                    else:
                        translate_obj = Translation(
                            video=video,
                            user=user,
                            transctipt=transcript,
                            parent=translation,
                            payload=translation.payload,
                            target_language=lang,
                            task=new_task,
                            translation_type=translation.translation_type,
                            status="TRANSLATION_REVIEWER_ASSIGNED"
                        )
                        translation_obj.save()
                        response = {"task_id": new_task.id,
                                    "translation_id": translate_obj.id,
                                    "data": translate_obj.payload}

                return Response(
                    response, status=status.HTTP_200_OK,
                )


    def create_transcription_task(self, video, user, task_type, request):
        task = Task.objects.filter(video=video)

        response = self.check_duplicate_task(task_type, task, user)
        if len(response) > 0:
            return Response(
                {"message": response["message"]},
                status=response["status"]
                )

        if "EDIT" in task_type:
            permitted = self.has_transcript_edit_permission(user, video)
        else:
            permitted = self.has_transcript_review_permission(user, video)

        if permitted:
            transcript = (Transcript.objects.filter(video=video)
                                           .first())

            if "EDIT" in task_type:
                transcript = (Transcript.objects.filter(video=video)
                                  .filter(status="TRANSCRIPTION_SELECT_SOURCE")
                                  .first())
                if transcript is not None:
                    new_task = Task(
                        task_type=task_type,
                        video=video,
                        created_by=request.user,
                        user=user,
                        status="NEW")
                    new_task.save()
                    transcript_obj = Transcript(
                        video=video,
                        user=user,
                        parent_transcript=transcript,
                        payload=transcript.payload,
                        language=video.language,
                        task=new_task,
                        transcript_type=transcript.transcript_type,
                        status="TRANSCRIPTION_EDITOR_ASSIGNED"
                    )
                    transcript_obj.save()
                    response = {"task_id": new_task.id,
                                "transcript_id": transcript_obj.id,
                                "data": transcript_obj.payload}
            else:
                transcript = (Transcript.objects.filter(video=video)
                                               .filter(status="TRANSCRIPTION_EDIT_COMPLETE")
                                               .first())
                if transcript is None:
                    return Response(
                        {"message": "Transcript review task can't be created, as editing is not done yet."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                else:
                    new_task = Task(
                        task_type=task_type,
                        video=video,
                        created_by=request.user,
                        user=user,
                        status="NEW")
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
                    response = {"task_id": new_task.id,
                                "transcript_id": transcript_obj.id,
                                "data": transcript_obj.payload}

            return Response(
                response, status=status.HTTP_200_OK,
            )


    def translation_mg(self, transcript, batch_size):
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


    def create_source_task(self, video, user, task_type, request, lang, verified_transcript):
        task = Task.objects.filter(video=video)

        response = self.check_duplicate_task(task_type, task, user)
        if len(response) > 0:
            return Response(
                {"message": response["message"]},
                status=response["status"]
                )

        payloads = {}
        response = {}
        payloads["MANUALLY_CREATED"] = ""
        if "TRANSCRIPT" in task_type:
            permitted = self.has_transcript_edit_permission(user, video)
            if permitted:
                new_task = Task(
                    task_type=task_type,
                    video=video,
                    created_by=request.user,
                    user=user,
                    status="NEW")
                new_task.save()
                # transcribed_data = make_asr_api_call(video.url, lang)
                transcribed_data = "Hello, World."
                if transcribed_data is not None:
                    payloads["MACHINE_GENERATED"] = transcribed_data
                else:
                    return Response(
                        {"message": "Error while calling ASR API"},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    )

                subtitles = video.subtitles
                if subtitles is not None:
                    payloads["ORIGINAL_SOURCE"] = subtitles

                response["task_id"] = new_task.id
                response["payloads"] = payloads
        else:
            permitted = self.has_translate_edit_permission(user, video)
            if permitted:
                new_task = Task(
                    task_type=task_type,
                    video=video,
                    created_by=request.user,
                    user=user,
                    status="NEW")
                new_task.save()

                transcript = self.check_transcript_exists(video, verified_transcript)
                subtitle_payload, is_machine_generated = get_subtitles_from_google_video(
                    video.url, lang
                )
                if subtitle_payload is not None:
                    payloads["ORIGINAL_SOURCE"] = subtitle_payload
                translation_machine_generated = translation_mg(video, transcript)
                payloads["MACHINE_GENERATED"] = translation_machine_generated
                response["payloads"] = payloads
                response["task_id"] = new_task.id
        return Response(
            response, status=status.HTTP_200_OK,
        )


    @swagger_auto_schema(
        method="post",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=["task_id", "type", "payload"],
            properties={
                "task_id": openapi.Schema(
                    type=openapi.TYPE_INTEGER,
                    description="Id of Task",
                ),
                "type": openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description="Type of task",
                ),
                "target_language": openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description="Source Language for Transcription tasks",
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
        task_id = request.data.get("task_id")
        payload = request.data.get("payload")
        type = request.data.get("type")

        if task_id is None or payload is None or type is None:
            return Response(
                {"message": "missing param : task_id or payload or type"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            task = Task.objects.get(pk=task_id)
        except Task.DoesNotExist:
            return Response(
                    {"message": "Task not found"},
                    status=status.HTTP_404_NOT_FOUND
                )

        if "TRANSCRIPTION" in task.task_type:
            response = generate_transcription(task.video, task.video.language, request.user, type, task, payload)
        else:
            response = self.generate_translation(task.video, task.video.language, transcript, request.user, type, task, payload)
        return  Response(
            response, status=status.HTTP_200_OK,
        )


    @is_project_owner
    def create(self, request, pk=None, *args, **kwargs):
        task_type = request.data.get("task_type")
        user_id = request.data.get("user_id")
        video_id = request.data.get("video_id")

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
                        {"message": "missing param : target language can't be None for translation tasks"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                verified_transcript = request.data.get("verified_transcript")

        try:
                video = Video.objects.get(pk=video_id)
        except Video.DoesNotExist:
                return Response(
                    {"message": "Video not found"},
                    status=status.HTTP_404_NOT_FOUND
                    )
        try:
                user = User.objects.get(pk=user_id)
        except User.DoesNotExist:
                return Response(
                    {"message": "User not found"},
                    status=status.HTTP_404_NOT_FOUND
                    )

        if "SELECT_SOURCE" in task_type:
            if "TRANSLATION" in task_type:
                lang = target_language
            else:
                lang = video.language
            return self.create_source_task(video, user, task_type, request, lang, verified_transcript)
        else:
            if "TRANSLATION" in task_type:
                return self.create_translation_task(video, user, target_language, task_type, request, verified_transcript)
            else:
                return self.create_transcription_task(video, user, task_type, request)
