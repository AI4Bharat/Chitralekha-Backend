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
from .decorators import is_project_owner
from users.serializers import UserFetchSerializer, UserProfileSerializer
from task.models import Task
from task.serializers import TaskSerializer, TaskStatusSerializer
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from django.db.models import Q
from config import *
from users.serializers import UserFetchSerializer


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
    @is_project_owner
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
            if not user:
                return Response(
                    {"message": "User doesnot exist"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            for prj_user in user:
                if prj_user in project.members.all():
                    return Response(
                        {"error": "member already added"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                project.members.add(prj_user)
                project.save()
            return Response(
                {"message": "Project members added successfully"},
                status=status.HTTP_200_OK,
            )
        except Project.DoesNotExist:
            return Response(
                {"error": "Project does not exist"},
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(
            {"error": "Method is not allowed"},
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
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
            200: "Project members added successfully",
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
    @is_project_owner
    def remove_project_members(self, request, pk=None, *args, **kwargs):
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
            if not user:
                return Response(
                    {"message": "User doesnot exist"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            for prj_user in user:
                if prj_user not in project.members.all():
                    return Response(
                        {"error": "member not added"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                project.members.remove(prj_user)
                project.save()
            return Response(
                {"message": "Project members removed successfully"},
                status=status.HTTP_200_OK,
            )

        except Project.DoesNotExist:
            return Response(
                {"error": "Project does not exist"},
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(
            {"error": "invalid method"},
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
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
                        {"error": "User is not a manager"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                if user in project.managers.all():
                    return Response(
                        {"error": "member already added"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                project.managers.add(user)
                project.save()
            return Response(
                {"message": "Project manager assigned successfully"},
                status=status.HTTP_200_OK,
            )

        except User.DoesNotExist:
            return Response(
                {"error": "User doesnot exist"},
                status=status.HTTP_404_NOT_FOUND,
            )
        except Project.DoesNotExist:
            return Response(
                {"error": "Project does not exist"},
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(
            {"error": "invalid method"},
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
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
                if user not in project.managers.all():
                    return Response(
                        {"error": "member not added"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                project.managers.remove(user)
                project.save()
            return Response(
                {"message": "Project manager unassigned successfully"},
                status=status.HTTP_200_OK,
            )

        except User.DoesNotExist:
            return Response(
                {"error": "User doesnot exist"},
                status=status.HTTP_404_NOT_FOUND,
            )
        except Project.DoesNotExist:
            return Response(
                {"error": "Project does not exist"},
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(
            {"error": "invalid method"},
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    # Add endpoint for archiving a project
    @action(
        detail=True,
        methods=["POST", "GET"],
        name="Archive Project",
        url_name="archive_project",
    )
    @is_project_owner
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
                {"error": "Project does not exist"},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(
            {"error": "invalid method"},
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    @action(
        detail=True,
        methods=["GET"],
        name="List Project Managers",
        url_name="list_project_managers",
    )
    @is_project_owner
    def list_project_managers(self, request, pk=None, *args, **kwargs):
        try:
            project = Project.objects.get(pk=pk)
            managers = User.objects.filter(role="PROJECT_MANAGER")
            serializer = UserProfileSerializer(managers, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except Project.DoesNotExist:
            return Response(
                {"error": "Project does not exist"},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(
            {"error": "invalid method"},
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
                        if "EDIT" in task_table["transcription"]:
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
                        if "EDIT" in task_table[task.target_language].task_type:
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
                task_table = self.video_status(tasks)
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
                {"error": "Project does not exist"},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(
            {"error": "invalid method"},
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
            tasks = Task.objects.filter(video_id__in=videos)
            if request.user in project.managers.all() or request.user.is_superuser:
                serializer = TaskSerializer(tasks, many=True)
            else:
                tasks_by_users = tasks.filter(user=request.user)
                serializer = TaskSerializer(tasks_by_users, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)

        except Project.DoesNotExist:
            return Response(
                {"error": "Project does not exist"},
                status=status.HTTP_404_NOT_FOUND,
            )
        except Exception as e:
            print(e)
            return Response(
                {"error": e},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(
            {"error": "invalid method"},
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

    @is_project_owner
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

    @is_project_owner
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
