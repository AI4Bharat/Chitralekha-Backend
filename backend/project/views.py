from rest_framework import viewsets
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import action
from rest_framework import status
from organization.models import Organization
from organization.decorators import is_organization_owner
from video.models import Video
from video.serializers import VideoSerializer
from users.models import User
from .models import Project
from .serializers import ProjectSerializer
from .decorators import is_project_owner, is_particular_project_owner
from users.serializers import UserFetchSerializer, UserProfileSerializer
from task.models import Task
from task.serializers import TaskSerializer, TaskStatusSerializer
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from django.db.models import Q, Count, Avg, F, FloatField, BigIntegerField, Sum, Value
from django.db.models.functions import Cast, Concat
from config import *
from users.serializers import UserFetchSerializer
from datetime import timedelta
from transcript.models import Transcript
from translation.models import Translation
import json
from translation.metadata import LANGUAGE_CHOICES


class ProjectViewSet(viewsets.ModelViewSet):
    """
    Viewset for Project CRUD
    """

    queryset = Project.objects.all()
    serializer_class = ProjectSerializer
    permission_classes = (IsAuthenticated,)

    @swagger_auto_schema(
        method="post",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                "user_id": openapi.Schema(type=openapi.TYPE_OBJECT),
            },
            required=["user_id"],
        ),
        responses={
            200: "Project members added successfully",
            400: "User doesnot exist",
            404: "Project does not exist",
            405: "Method is not allowed",
        },
    )
    @action(
        detail=True,
        methods=["POST"],
        name="Add Project members",
        url_name="add_project_members",
    )
    @is_particular_project_owner
    def add_project_members(self, request, pk=None, *args, **kwargs):

        try:
            project = Project.objects.get(pk=pk)
            if "user_id" in dict(request.data):
                ids = request.data.get("user_id", "")
            else:
                return Response(
                    {"message": "key doesnot match"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            user = User.objects.filter(id__in=ids)
            if user and user.count() == len(ids):
                if project.members:
                    for member in project.members.all():
                        if member.id in ids:
                            ids.remove(member.id)
                    if ids:
                        project.members.add(*ids)
                        return Response(
                            {"message": "Project members added successfully"},
                            status=status.HTTP_200_OK,
                        )

                    else:
                        return Response(
                            {"message": "Project members already exists"},
                            status=status.HTTP_200_OK,
                        )
                else:
                    project.members.add(*ids)
                    return Response(
                        {"message": "Project members added successfully"},
                        status=status.HTTP_200_OK,
                    )
            else:
                return Response(
                    {"message": "User doesnot exist"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        except Project.DoesNotExist:
            return Response(
                {"message": "Project does not exist"},
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(
            {"message": "Method is not allowed"},
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    def get_tasks_assigned_to_member(self, project, user):
        videos = Video.objects.filter(project_id=project)
        tasks = (
            Task.objects.filter(video_id__in=videos)
            .filter(user=user)
            .exclude(status="COMPLETE")
        )
        response = [
            {
                "task_type": task.get_task_type_label,
                "target_language": task.get_target_language_label,
                "video_name": task.video.name,
                "id": task.id,
            }
            for task in tasks
        ]
        return response

    @swagger_auto_schema(
        method="post",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                "user_id": openapi.Schema(type=openapi.TYPE_OBJECT),
            },
            required=["user_id"],
        ),
        responses={
            200: "Project members removed successfully",
            400: "User doesnot exist",
            404: "Project does not exist",
            405: "Method is not allowed",
        },
    )
    @action(
        detail=True,
        methods=["POST"],
        name="Remove Project members",
        url_name="remove_project_members",
    )
    @is_particular_project_owner
    def remove_project_members(self, request, pk=None, *args, **kwargs):
        try:
            project = Project.objects.get(pk=pk)
        except Project.DoesNotExist:
            return Response(
                {"message": "Project does not exist"},
                status=status.HTTP_404_NOT_FOUND,
            )

        if "user_id" not in request.data:
            return Response(
                {"message": "missing param : user_ids"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        ids = request.data.get("user_id")
        invalid_users = []
        valid_users = []
        list_tasks = []

        for id in ids:
            try:
                user = User.objects.get(pk=id)
                valid_users.append(user)
            except User.DoesNotExist:
                invalid_users.append(id)
                ids.remove(id)

        if len(invalid_users) > 0:
            return Response(
                {"message": "Users doesnot exist."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        for user in valid_users:
            if project.managers and user in project.managers.all():
                response = self.get_tasks_assigned_to_member(project, user)
                if len(response) > 0:
                    return Response(
                        {
                            "message": "Can't delete member as tasks are assigned to this member.",
                            "response": response,
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                if len(project.managers.all()) > 1:
                    project.managers.remove(user.id)
                    project.members.remove(user.id)
                else:
                    invalid_users.append(user)
            elif project.members and user in project.members.all():
                response = self.get_tasks_assigned_to_member(project, user)
                if len(response) > 0:
                    return Response(
                        {
                            "message": "Can't delete member as tasks are assigned to this member.",
                            "response": response,
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                project.members.remove(user.id)
            else:
                return Response(
                    {"message": "User is not a member or manager of the project."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        if len(invalid_users) > 0:
            return Response(
                {
                    "message": "Can't delete this user, {0} as atleast one manager is required in the project.".format(
                        invalid_users[0].username
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(
            {"message": "Project members removed successfully"},
            status=status.HTTP_200_OK,
        )

    @swagger_auto_schema(
        method="post",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                "user_id": openapi.Schema(type=openapi.TYPE_OBJECT),
            },
            required=["user_id"],
        ),
        responses={
            200: "Project manager assigned successfully",
            400: "User doesnot exist",
            404: "Project does not exist",
            405: "Method is not allowed",
        },
    )
    @action(
        detail=True,
        methods=["POST"],
        name="Assign Project manager",
        url_name="assign_project_manager",
    )
    @is_organization_owner
    def assign_project_manager(self, request, pk=None, *args, **kwargs):
        if "user_id" in dict(request.data):
            ids = request.data.get("user_id", "")
        else:
            return Response(
                {"message": "key doesnot match"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            project = Project.objects.get(pk=pk)
            for prj_user in ids:
                user = User.objects.get(id=prj_user)
                if user.role != (
                    User.PROJECT_MANAGER
                    or User.ADMIN
                    or User.ORG_OWNER
                    or User.is_superuser
                ):
                    return Response(
                        {"message": "User is not a manager"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                if project.managers:
                    for manager in project.managers.all():
                        if manager.id in ids:
                            ids.remove(manager.id)
                    if ids:
                        project.managers.add(*ids)
                        return Response(
                            {"message": "Project managers added successfully"},
                            status=status.HTTP_200_OK,
                        )
                    else:
                        return Response(
                            {"message": "Project managers already exists"},
                            status=status.HTTP_200_OK,
                        )
                else:
                    project.managers.add(*ids)
                    return Response(
                        {"message": "Project managers added successfully"},
                        status=status.HTTP_200_OK,
                    )

        except User.DoesNotExist:
            return Response(
                {"message": "User doesnot exist"},
                status=status.HTTP_404_NOT_FOUND,
            )
        except Project.DoesNotExist:
            return Response(
                {"message": "Project does not exist"},
                status=status.HTTP_404_NOT_FOUND,
            )

    @swagger_auto_schema(
        method="post",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                "user_id": openapi.Schema(type=openapi.TYPE_OBJECT),
            },
            required=["user_id"],
        ),
        responses={
            200: "Project mangers unassigned successfully",
            400: "User doesnot exist",
            404: "Project does not exist",
            405: "Method is not allowed",
        },
    )
    @action(
        detail=True,
        methods=["POST"],
        name="Unassign Project manager",
        url_name="unassign_project_manager",
    )
    @is_organization_owner
    def unassign_project_manager(self, request, pk=None, *args, **kwargs):
        if "user_id" in dict(request.data):
            ids = request.data.get("user_id", "")
        else:
            return Response(
                {"message": "key doesnot match"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            project = Project.objects.get(pk=pk)
            for prj_user in ids:
                user = User.objects.get(id=prj_user)
                if user.role != (
                    User.PROJECT_MANAGER
                    or User.ADMIN
                    or User.ORG_OWNER
                    or User.is_superuser
                ):
                    return Response(
                        {"message": "User is not a manager"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                if project.managers and len(project.managers.all()) > 0:
                    for manager in project.managers.all():
                        if manager.id in ids:
                            ids.append(manager.id)
                    if (
                        ids
                        and len(ids) != len(project.managers.all())
                        and user.role
                        == (
                            User.PROJECT_MANAGER
                            or User.ADMIN
                            or User.ORG_OWNER
                            or User.is_superuser
                        )
                    ):
                        project.managers.remove(*ids)
                        return Response(
                            {"message": "Project managers removed successfully"},
                            status=status.HTTP_200_OK,
                        )
                    else:
                        return Response(
                            {"message": "Project managers doesnot exists"},
                            status=status.HTTP_200_OK,
                        )
                else:
                    return Response(
                        {"message": "Project managers not assigned"},
                        status=status.HTTP_200_OK,
                    )
        except User.DoesNotExist:
            return Response(
                {"message": "User doesnot exist"},
                status=status.HTTP_404_NOT_FOUND,
            )
        except Project.DoesNotExist:
            return Response(
                {"message": "Project does not exist"},
                status=status.HTTP_404_NOT_FOUND,
            )

    # Add endpoint for archiving a project
    @action(
        detail=True,
        methods=["POST", "GET"],
        name="Archive Project",
        url_name="archive_project",
    )
    @is_particular_project_owner
    def archive_project(self, request, pk=None, *args, **kwargs):
        try:
            project = Project.objects.get(pk=pk)
            project.is_archived = not project.is_archived
            project.save()
            return Response(
                {"message": "Project archived successfully"},
                status=status.HTTP_200_OK,
            )
        except Project.DoesNotExist:
            return Response(
                {"message": "Project does not exist"},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(
            {"message": "invalid method"},
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    @action(
        detail=True,
        methods=["GET"],
        name="List Project Managers",
        url_name="list_project_managers",
    )
    @is_particular_project_owner
    def list_project_managers(self, request, pk=None, *args, **kwargs):
        try:
            project = Project.objects.get(pk=pk)
            managers = User.objects.filter(role="PROJECT_MANAGER")
            serializer = UserProfileSerializer(managers, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except Project.DoesNotExist:
            return Response(
                {"message": "Project does not exist"},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(
            {"message": "invalid method"},
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    def video_status(self, tasks):
        task_table = {}
        for task in tasks:
            if "TRANSCRIPTION" in task.task_type:
                if task.status in ["INPROGRESS", "COMPLETE"]:
                    if "transcription" not in task_table.keys():
                        task_table["transcription"] = task
                    else:
                        if "EDIT" in task_table["transcription"].task_type:
                            task_table["transcription"] = task
                else:
                    task_table["transcription"] = ("NEW", task)

        for task in tasks:
            if "TRANSCRIPTION" in task.task_type:
                continue
            if "TRANSLATION" in task.task_type:
                if task.status in ["INPROGRESS", "COMPLETE"]:
                    if task.target_language not in task_table:
                        task_table[task.target_language] = task
                    else:
                        if type(task_table[task.target_language]) != tuple:
                            if "EDIT" in task_table[task.target_language].task_type:
                                task_table[task.target_language] = task
                        else:
                            if "EDIT" in task.task_type:
                                task_table[task.target_language] = task
                else:
                    if task.target_language in task_table:
                        if (
                            type(task_table[task.target_language]) != tuple
                            and "REVIEW" in task_table[task.target_language].task_type
                        ):
                            task_table[task.target_language] = task
                    elif "transcription" in task_table:
                        if type(task_table["transcription"]) == tuple:
                            task_table[task.target_language] = ("NEW", task)
                        else:
                            task_table[task.target_language] = (
                                task_table["transcription"].get_task_status,
                                task,
                            )
                    else:
                        task_table[task.target_language] = ("NEW", task)
        return task_table

    def check_if_last_task_in_workflow(self, task_obj):
        task = task_obj["task"]
        if task.task_type == "TRANSLATION_REVIEW":
            return True
        elif task.task_type == "TRANSLATION_EDIT":
            if (
                Task.objects.filter(task_type="TRANSLATION_REVIEW")
                .filter(video=task.video)
                .first()
                is None
            ):
                return True
            else:
                return False
        elif task.task_type == "TRANSCRIPTION_REVIEW":
            if (
                Task.objects.filter(
                    task_type__in=["TRANSLATION_REVIEW", "TRANSLATION_EDIT"]
                )
                .filter(video=task.video)
                .first()
                is None
            ):
                return True
            else:
                return False
        elif task.task_type == "TRANSCRIPTION_EDIT":
            if (
                Task.objects.filter(
                    task_type__in=[
                        "TRANSLATION_REVIEW",
                        "TRANSLATION_EDIT",
                        "TRANSCRIPTION_REVIEW",
                    ]
                )
                .filter(video=task.video)
                .first()
                is None
            ):
                return True
            else:
                return False
        else:
            print("Not a valid type")
            return False

    # Add endpoint to list all related videos of a project (project_id)
    @action(
        detail=True,
        methods=["GET"],
        name="List Project Videos",
        url_name="list_project_videos",
    )
    def list_project_videos(self, request, pk=None, *args, **kwargs):
        try:
            project = Project.objects.get(pk=pk)
            videos = Video.objects.filter(project_id=pk)
            serializer = VideoSerializer(videos, many=True)
            video_data = []
            for video in videos:
                tasks = Task.objects.filter(video=video)
                video_serializer = VideoSerializer(video).data
                try:
                    task_table = self.video_status(tasks)
                except:
                    video_serializer["status"] = []
                    video_data.append(video_serializer)
                    continue
                tasks_to_send = []
                if len(task_table) == 1:
                    if "transcription" in task_table.keys():
                        task_obj = task_table["transcription"]
                        if type(task_obj) != tuple:
                            tasks_to_send.append(
                                {
                                    "task": task_obj,
                                    "language_pair": task_obj.get_language_pair_label,
                                    "task_status": task_obj.get_task_status,
                                    "user": UserFetchSerializer(task_obj.user).data,
                                    "created_at": task_obj.created_at,
                                }
                            )
                        else:
                            tasks_to_send.append(
                                {
                                    "task": task_obj[1],
                                    "language_pair": task_obj[
                                        1
                                    ].get_language_pair_label,
                                    "task_status": task_obj[0],
                                    "user": UserFetchSerializer(task_obj[1].user).data,
                                    "created_at": task_obj[1].created_at,
                                }
                            )
                if len(task_table) > 1:
                    if "transcription" in task_table.keys():
                        del task_table["transcription"]
                    all_statuses = set()
                    for target_language, task_obj in task_table.items():
                        if type(task_obj) != tuple:
                            all_statuses.add(task_obj.status)
                            tasks_to_send.append(
                                {
                                    "task": task_obj,
                                    "language_pair": task_obj.get_language_pair_label,
                                    "task_status": task_obj.get_task_status,
                                    "user": UserFetchSerializer(task_obj.user).data,
                                    "created_at": task_obj.created_at,
                                }
                            )
                        else:
                            all_statuses.add(task_obj[1].status)
                            tasks_to_send.append(
                                {
                                    "task": task_obj[1],
                                    "language_pair": task_obj[
                                        1
                                    ].get_language_pair_label,
                                    "task_status": task_obj[0],
                                    "user": UserFetchSerializer(task_obj[1].user).data,
                                    "created_at": task_obj[1].created_at,
                                }
                            )

                for task in tasks_to_send:
                    if (
                        self.check_if_last_task_in_workflow(task)
                        and "COMPLETE" in task["task_status"]
                        and task["task"].get_task_type_label in task["task_status"]
                    ):
                        task["task_status"] = "COMPLETE"
                    del task["task"]

                video_serializer["status"] = tasks_to_send
                video_data.append(video_serializer)
            return Response(video_data, status=status.HTTP_200_OK)
        except Project.DoesNotExist:
            return Response(
                {"message": "Project does not exist"},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(
            {"message": "invalid method"},
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    @action(
        detail=True,
        methods=["GET"],
        name="List Project Task",
        url_name="list_project_Task",
    )
    def list_project_tasks(self, request, pk=None, *args, **kwargs):
        try:
            project = Project.objects.get(pk=pk)
            videos = Video.objects.filter(project_id=pk).values_list("id", flat=True)
            tasks = Task.objects.filter(video_id__in=videos).order_by("-updated_at")
            if request.user in project.managers.all() or request.user.is_superuser:
                serializer = TaskSerializer(tasks, many=True)
                serialized_dict = json.loads(json.dumps(serializer.data))
                for data in serialized_dict:
                    buttons = {
                        "Edit": False,
                        "Preview": False,
                        "Export": False,
                        "Update": False,
                        "View": False,
                        "Delete": False,
                    }
                    buttons["Update"] = True
                    buttons["Delete"] = True
                    if data["status"] == "COMPLETE":
                        buttons["Export"] = True
                        buttons["Preview"] = True
                        buttons["Edit"] = False
                        buttons["Update"] = False
                    if data["user"]["email"] == request.user.email:
                        if data["status"] != "COMPLETE":
                            buttons["Edit"] = True
                        if data["status"] == "SELECTED_SOURCE":
                            buttons["View"] = True
                    data["buttons"] = buttons
            else:
                tasks_by_users = tasks.filter(user=request.user).order_by("-updated_at")
                serializer = TaskSerializer(tasks_by_users, many=True)
                serialized_dict = json.loads(json.dumps(serializer.data))
                for data in serialized_dict:
                    buttons = {
                        "Edit": False,
                        "Preview": False,
                        "Export": False,
                        "Update": False,
                        "Create": False,
                        "Delete": False,
                    }
                    if data["status"] == "COMPLETE":
                        buttons["Edit"] = False
                        buttons["Export"] = True
                        buttons["Preview"] = True
                        buttons["Update"] = False
                    if data["user"]["email"] == request.user.email:
                        if data["status"] != "COMPLETE":
                            buttons["Edit"] = True
                        if data["status"] == "SELECTED_SOURCE":
                            buttons["View"] = True
                    data["buttons"] = buttons
            return Response(serialized_dict, status=status.HTTP_200_OK)

        except Project.DoesNotExist:
            return Response(
                {"message": "Project does not exist"},
                status=status.HTTP_404_NOT_FOUND,
            )
        except Exception as e:
            print(e)
            return Response(
                {"message": e},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(
            {"message": "invalid method"},
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    @is_organization_owner
    def create(self, request, pk=None, *args, **kwargs):
        """
        Create a Project
        """
        title = request.data.get("title")
        organization_id = request.data.get("organization_id")
        managers_id = request.data.get("managers_id")
        description = request.data.get("description")
        default_transcript_type = request.data.get("default_transcript_type")
        default_translation_type = request.data.get("default_translation_type")
        default_task_types = request.data.get("default_task_types")
        default_target_languages = None

        if title is None or organization_id is None or len(managers_id) == 0:
            return Response(
                {"message": "missing param : title or organization_id or managers"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            organization = Organization.objects.get(pk=organization_id)
        except Organization.DoesNotExist:
            return Response(
                {"message": "Organization not found"}, status=status.HTTP_404_NOT_FOUND
            )

        if default_task_types is not None and (
            "TRANSLATION_EDIT" or "TRANSLATION_REVIEW" in default_task_types
        ):
            default_target_languages = request.data.get("default_target_languages")
            if default_target_languages is None:
                return Response(
                    {
                        "message": "missing param : Target Language can't be None of Translation task is selected."
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

        project = Project(
            title=title,
            organization_id=organization,
            created_by=request.user,
            default_transcript_type=default_transcript_type,
            default_translation_type=default_translation_type,
            default_task_types=default_task_types,
            default_target_languages=default_target_languages,
        )
        project.save()

        for manager_id in managers_id:
            managers = []
            try:
                user = User.objects.get(pk=manager_id)
            except User.DoesNotExist:
                return Response(
                    {"message": "User not found"}, status=status.HTTP_404_NOT_FOUND
                )
            project.managers.add(user)
            project.members.add(user)

        response = {
            "project_id": project.id,
            "message": "Project is successfully created.",
        }
        return Response(
            response,
            status=status.HTTP_200_OK,
        )

    @is_particular_project_owner
    def partial_update(self, request, pk=None, *args, **kwargs):
        """
        Update project details
        """
        title = request.data.get("title")
        managers_id = request.data.get("managers_id")
        description = request.data.get("description")
        default_transcript_type = request.data.get("default_transcript_type")
        default_translation_type = request.data.get("default_translation_type")
        default_target_languages = request.data.get("default_target_languages")
        default_task_types = request.data.get("default_task_types")
        default_task_eta = request.data.get("default_task_eta")
        default_task_priority = request.data.get("default_task_priority")
        default_task_description = request.data.get("default_task_description")

        try:
            project = Project.objects.get(pk=pk)
        except Project.DoesNotExist:
            return Response(
                {"message": "Project not found"}, status=status.HTTP_404_NOT_FOUND
            )

        if title is not None:
            project.title = title

        if managers_id is not None and len(managers_id) > 0:
            project.managers.set([])
            for manager_id in managers_id:
                try:
                    user = User.objects.get(pk=manager_id)
                except User.DoesNotExist:
                    return Response(
                        {"message": "User not found"}, status=status.HTTP_404_NOT_FOUND
                    )
                project.managers.add(user)
                if user not in project.members.all():
                    project.members.add(user)

        if default_task_types is not None and len(default_task_types) > 0:
            project.default_task_types = None
            project.default_task_types = default_task_types

        if project.default_task_types is not None and (
            "TRANSLATION_EDIT" or "TRANSLATION_REVIEW" in project.default_task_types
        ):
            default_target_languages = request.data.get("default_target_languages")
            if default_target_languages is None:
                return Response(
                    {
                        "message": "missing param : Target Language can't be None if Translation task is selected."
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            project.default_target_languages = default_target_languages

        if default_task_eta is not None:
            project.default_eta = default_task_eta

        if default_transcript_type is not None:
            project.default_transcript_type = default_transcript_type

        if default_translation_type is not None:
            project.default_translation_type = default_translation_type

        if default_task_priority is not None:
            project.default_priority = default_task_priority

        if default_task_description is not None:
            project.default_description = default_task_description

        if description is not None:
            project.description = description

        project.save()

        return Response(
            {"message": "Project updated successfully."}, status=status.HTTP_200_OK
        )

    @is_particular_project_owner
    def update(self, request, pk=None, *args, **kwargs):
        super().update(request, *args, **kwargs)
        return Response(
            {"message": "Project updated successfully."}, status=status.HTTP_200_OK
        )

    @is_organization_owner
    def destroy(self, request, pk=None, *args, **kwargs):
        """
        Delete a project
        """
        super().destroy(request, *args, **kwargs)
        return Response(
            {"message": "Project deleted successfully."},
            status=status.HTTP_200_OK,
        )

    @swagger_auto_schema(
        method="get",
        manual_parameters=[
            openapi.Parameter(
                "task_type",
                openapi.IN_QUERY,
                description=("An integer to identify the task"),
                type=openapi.TYPE_STRING,
                required=False,
            ),
        ],
        responses={200: "Get members of a project"},
    )
    @action(
        detail=True, methods=["GET"], name="Get Project members", url_name="members"
    )
    def users(self, request, pk=None, *args, **kwargs):
        try:
            project = Project.objects.get(pk=pk)
        except Project.DoesNotExist:
            return Response(
                {"message": "Project not found"}, status=status.HTTP_404_NOT_FOUND
            )
        users = project.members.all()
        serializer = UserFetchSerializer(users, many=True)

        if "task_type" in request.query_params:
            task_type = request.query_params["task_type"]
            try:
                users = project.members.all()
                if task_type == "TRANSCRIPTION_EDIT":
                    user_by_roles = users.filter(
                        Q(role="PROJECT_MANAGER")
                        | Q(role="ORG_OWNER")
                        | Q(role="UNIVERSAL_EDITOR")
                        | Q(role="TRANSCRIPT_EDITOR")
                        | Q(role="TRANSCRIPT_REVIEWER")
                        | Q(is_superuser=True)
                    )
                elif task_type == "TRANSCRIPTION_REVIEW":
                    user_by_roles = users.filter(
                        Q(role="PROJECT_MANAGER")
                        | Q(role="ORG_OWNER")
                        | Q(role="UNIVERSAL_EDITOR")
                        | Q(role="TRANSCRIPT_REVIEWER")
                        | Q(is_superuser=True)
                    )
                elif task_type == "TRANSLATION_EDIT":
                    user_by_roles = users.filter(
                        Q(role="PROJECT_MANAGER")
                        | Q(role="ORG_OWNER")
                        | Q(role="UNIVERSAL_EDITOR")
                        | Q(role="TRANSLATION_EDITOR")
                        | Q(role="TRANSLATION_REVIEWER")
                        | Q(is_superuser=True)
                    )
                else:
                    user_by_roles = users.filter(
                        Q(role="PROJECT_MANAGER")
                        | Q(role="ORG_OWNER")
                        | Q(role="UNIVERSAL_EDITOR")
                        | Q(role="TRANSLATION_REVIEWER")
                        | Q(is_superuser=True)
                    )
                serializer = UserFetchSerializer(user_by_roles, many=True)
            except Task.DoesNotExist:
                return Response(
                    {"message": "Task not found"}, status=status.HTTP_404_NOT_FOUND
                )
        return Response(serializer.data)

    @action(
        detail=True,
        methods=["GET"],
        name="Display non members of a project",
        url_name="get_non_members",
    )
    def get_non_members(self, request, pk=None, *args, **kwargs):
        try:
            project = Project.objects.get(pk=pk)
        except Project.DoesNotExist:
            return Response(
                {"message": "Project not found"}, status=status.HTTP_404_NOT_FOUND
            )
        users = User.objects.filter(organization_id=project.organization_id).exclude(
            pk__in=project.members.all()
        )
        serializer = UserFetchSerializer(users, many=True)
        return Response(serializer.data)

    @swagger_auto_schema(method="get", responses={200: "Success"})
    @action(
        detail=True,
        methods=["GET"],
        name="Get Report Users",
        url_name="get_report_users",
    )
    @is_particular_project_owner
    def get_report_users(self, request, pk=None, *args, **kwargs):
        try:
            prj = Project.objects.get(pk=pk)
        except Project.DoesNotExist:
            return Response(
                {"message": "Project not found"}, status=status.HTTP_404_NOT_FOUND
            )
        project_members = (
            User.objects.filter(projects__pk=pk)
            .values(name=Concat("first_name", Value(" "), "last_name"), mail=F("email"))
            .order_by("mail")
        )
        user_statistics = (
            project_members.annotate(tasks_assigned_count=Count("task"))
            .annotate(
                tasks_completed_count=Count("task", filter=Q(task__status="COMPLETE"))
            )
            .annotate(
                task_completion_percentage=Cast(
                    F("tasks_completed_count"), FloatField()
                )
                / Cast(F("tasks_assigned_count"), FloatField())
                * 100
            )
            .annotate(
                average_completion_time=Avg(
                    F("task__updated_at") - F("task__created_at"),
                    filter=Q(task__status="COMPLETE"),
                )
            )
            .exclude(tasks_assigned_count=0)
        )
        user_data = []
        for elem in user_statistics:
            avg_time = (
                None
                if elem["average_completion_time"] is None
                else round(elem["average_completion_time"].total_seconds() / 3600, 3)
            )
            user_dict = {
                "name": {"value": elem["name"], "label": "Name"},
                "mail": {"value": elem["mail"], "label": "Email"},
                "tasks_assigned_count": {
                    "value": elem["tasks_assigned_count"],
                    "label": "Assigned Tasks",
                },
                "tasks_completed_count": {
                    "value": elem["tasks_completed_count"],
                    "label": "Completed Tasks",
                },
                "tasks_completion_perc": {
                    "value": round(elem["task_completion_percentage"], 2),
                    "label": "Task Completion Index(%)",
                },
                "avg_comp_time": {"value": avg_time, "label": "Avg. Completion Time"},
            }
            user_data.append(user_dict)
        return Response(user_data, status=status.HTTP_200_OK)

    @swagger_auto_schema(method="get", responses={200: "Success"})
    @action(
        detail=True,
        methods=["GET"],
        name="Get Report Languages",
        url_name="get_report_langs",
    )
    @is_particular_project_owner
    def get_report_languages(self, request, pk=None, *args, **kwargs):
        try:
            prj = Project.objects.get(pk=pk)
        except Project.DoesNotExist:
            return Response(
                {"message": "Project not found"}, status=status.HTTP_404_NOT_FOUND
            )
        prj_videos = Video.objects.filter(project_id=pk)
        prj_transcriptions = (
            Transcript.objects.filter(video__in=prj_videos)
            .filter(status="TRANSCRIPTION_EDIT_COMPLETE")
            .values("language")
        )
        transcript_statistics = prj_transcriptions.annotate(
            total_duration=Sum(F("video__duration"))
        ).order_by("-total_duration")
        prj_translations = (
            Translation.objects.filter(video__in=prj_videos)
            .filter(status="TRANSLATION_EDIT_COMPLETE")
            .values(
                src_language=F("video__language"), tgt_language=F("target_language")
            )
        )
        translation_statistics = (
            prj_translations.annotate(transcripts_translated=Count("id"))
            .annotate(translation_duration=Sum(F("video__duration")))
            .order_by("-translation_duration")
        )

        transcript_data = []
        for elem in transcript_statistics:
            transcript_dict = {
                "language": {
                    "value": dict(LANGUAGE_CHOICES)[elem["language"]],
                    "label": "Media Language",
                },
                "total_duration": {
                    "value": round(elem["total_duration"].total_seconds() / 3600, 3),
                    "label": "Transcripted Duration (Hours)",
                },
            }
            transcript_data.append(transcript_dict)

        translation_data = []
        for elem in translation_statistics:
            translation_dict = {
                "src_language": {
                    "value": dict(LANGUAGE_CHOICES)[elem["src_language"]],
                    "label": "Src Language",
                },
                "tgt_language": {
                    "value": dict(LANGUAGE_CHOICES)[elem["tgt_language"]],
                    "label": "Tgt Language",
                },
                "translation_duration": {
                    "value": round(
                        elem["translation_duration"].total_seconds() / 3600, 3
                    ),
                    "label": "Translated Duration (Hours)",
                },
                "transcripts_translated": {
                    "value": elem["transcripts_translated"],
                    "label": "Translation Tasks Count",
                },
            }
            translation_data.append(translation_dict)
        res = {
            "transcript_stats": transcript_data,
            "translation_stats": translation_data,
        }
        return Response(res, status=status.HTTP_200_OK)
