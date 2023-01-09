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
from task.serializers import TaskSerializer
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from django.db.models import Q
from config import *


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
            if user and user.count() == len(ids):
                if project.members and len(project.members.all()) > 0 and len(ids) > 0:
                    for member in project.members.all():
                        if member.id in ids:
                            if member.id in project.managers.all().values_list(
                                "id", flat=True
                            ):

                                if (
                                    len(project.managers.all()) > 1
                                    and len(project.members.all()) > 1
                                ):
                                    project.managers.remove(member.id)
                                    project.members.remove(member.id)
                                    ids.append(member.id)
                                else:

                                    return Response(
                                        {
                                            "message": "Project must have atleast one manager and one member"
                                        },
                                        status=status.HTTP_400_BAD_REQUEST,
                                    )
                            else:
                                project.members.remove(member.id)
                                ids.append(member.id)

                    if ids and len(ids) != len(project.members.all()):
                        project.members.remove(*ids)
                        return Response(
                            {"message": "Project members removed successfully"},
                            status=status.HTTP_200_OK,
                        )
                    else:
                        return Response(
                            {"message": "Project has no members"},
                            status=status.HTTP_200_OK,
                        )
                else:
                    return Response(
                        {"message": "Project members are already removed"},
                        status=status.HTTP_200_OK,
                    )
            else:
                return Response(
                    {"message": "User doesnot exist"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        except Project.DoesNotExist:
            return Response(
                {"error": "Project does not exist"},
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
                {"error": "User doesnot exist"},
                status=status.HTTP_404_NOT_FOUND,
            )
        except Project.DoesNotExist:
            return Response(
                {"error": "Project does not exist"},
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
                        {"error": "User is not a manager"},
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
                {"error": "User doesnot exist"},
                status=status.HTTP_404_NOT_FOUND,
            )
        except Project.DoesNotExist:
            return Response(
                {"error": "Project does not exist"},
                status=status.HTTP_404_NOT_FOUND,
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
    def update(self, request, pk=None, *args, **kwargs):
        """
        Update project details
        """
        title = request.data.get("title")
        managers_id = request.data.get("managers_id")
        description = request.data.get("description")
        default_transcript_type = request.data.get("default_transcript_type")
        default_translation_type = request.data.get("default_translation_type")
        default_task_types = request.data.get("default_task_types")
        default_task_eta = request.data.get("default_task_eta")
        default_task_priority = request.data.get("default_task_priority")
        default_task_description = request.data.get("default_task_description")

    @is_project_owner
    def partial_update(self, request, pk=None, *args, **kwargs):
        super().partial_update(request, *args, **kwargs)
        return Response(
            {"message": "Project updated successfully."}, status=status.HTTP_200_OK
        )

    @is_project_owner
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
