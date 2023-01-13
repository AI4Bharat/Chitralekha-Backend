from rest_framework import viewsets
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import action
from rest_framework import status
from users.serializers import UserFetchSerializer
from users.models import User
from .models import Organization
from .serializers import OrganizationSerializer
from .decorators import (
    is_organization_owner,
    is_particular_organization_owner,
    is_admin,
)
from task.models import Task
from task.serializers import TaskSerializer
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from project.serializers import ProjectSerializer
from project.models import Project
from config import *
from django.db.models import Q, Count, Avg, F, FloatField, BigIntegerField, Sum
from django.db.models.functions import Cast
from datetime import timedelta
from video.models import Video
from transcript.models import Transcript
from translation.models import Translation


class OrganizationViewSet(viewsets.ModelViewSet):
    """
    Viewset for Organization CRUD
    """

    queryset = Organization.objects.all()
    serializer_class = OrganizationSerializer
    permission_classes = (IsAuthenticated,)

    @is_admin
    def create(self, request, pk=None, *args, **kwargs):
        """
        Create an Organization
        """
        title = request.data.get("title")
        email_domain_name = request.data.get("email_domain_name")
        organization_owner = request.data.get("organization_owner")
        default_transcript_type = request.data.get("default_transcript_type")
        default_translation_type = request.data.get("default_translation_type")
        default_task_types = request.data.get("default_task_types")
        default_target_languages = None

        if title is None or email_domain_name is None or organization_owner is None:
            return Response(
                {
                    "message": "missing param : title or email_domain_name or organization_owner"
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            organization_owner = User.objects.get(pk=organization_owner)
        except User.DoesNotExist:
            return Response(
                {"message": "User not found"}, status=status.HTTP_404_NOT_FOUND
            )

        if organization_owner.is_superuser == False and organization_owner.role != (
            User.ADMIN and User.ORG_OWNER
        ):
            return Response(
                {"message": "This user can't be the organization owner."},
                status=status.HTTP_403_FORBIDDEN,
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

        try:
            organization = Organization(
                title=title,
                email_domain_name=email_domain_name,
                organization_owner=organization_owner,
                created_by=request.user,
                default_transcript_type=default_transcript_type,
                default_translation_type=default_translation_type,
                default_task_types=default_task_types,
                default_target_languages=default_target_languages,
            )
            organization.save()
        except:
            return Response(
                {"message": "Organization can't be created"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        organization_owner.organization = organization
        organization_owner.save()

        response = {
            "organization_id": organization.id,
            "message": "Organization is successfully created.",
        }

        return Response(
            response,
            status=status.HTTP_200_OK,
        )

    @is_particular_organization_owner
    def update(self, request, pk=None, *args, **kwargs):
        return super().update(request, *args, **kwargs)

    @is_particular_organization_owner
    def partial_update(self, request, pk=None, *args, **kwargs):
        title = request.data.get("title")
        email_domain_name = request.data.get("email_domain_name")
        description = request.data.get("description")
        default_transcript_type = request.data.get("default_transcript_type")
        default_translation_type = request.data.get("default_translation_type")
        default_target_languages = request.data.get("default_target_languages")
        default_task_types = request.data.get("default_task_types")
        org_owner = request.data.get("organization_owner")

        try:
            organization = Organization.objects.get(pk=pk)
        except Organization.DoesNotExist:
            return Response(
                {"message": "Organization not found"}, status=status.HTTP_404_NOT_FOUND
            )

        if title is not None:
            organization.title = title

        if email_domain_name is not None:
            organization.email_domain_name = email_domain_name

        if org_owner is not None:
            try:
                user = User.objects.get(pk=org_owner)
            except User.DoesNotExist:
                return Response(
                    {"message": "User not found"}, status=status.HTTP_404_NOT_FOUND
                )
            organization.organization_owner = user
            user.organization = organization

        if default_task_types is not None and len(default_task_types) > 0:
            organization.default_task_types = None
            organization.default_task_types = default_task_types

        if organization.default_task_types is not None and (
            "TRANSLATION_EDIT"
            or "TRANSLATION_REVIEW" in organization.default_task_types
        ):
            default_target_languages = request.data.get("default_target_languages")
            if default_target_languages is None:
                return Response(
                    {
                        "message": "missing param : Target Language can't be None if Translation task is selected."
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            organization.default_target_languages = default_target_languages

        if default_transcript_type is not None:
            organization.default_transcript_type = default_transcript_type

        if default_translation_type is not None:
            organization.default_translation_type = default_translation_type

        organization.save()

        return Response(
            {"message": "Organization updated successfully."}, status=status.HTTP_200_OK
        )

    @is_admin
    def destroy(self, request, pk=None, *args, **kwargs):
        super().destroy(request, *args, **kwargs)
        return Response(
            {"message": "Organization deleted successfully."},
            status=status.HTTP_200_OK,
        )

    @swagger_auto_schema(
        method="get",
        manual_parameters=[
            openapi.Parameter(
                "role",
                openapi.IN_QUERY,
                description=("A string to get the role type e.g. PROJECT_MANAGER"),
                type=openapi.TYPE_STRING,
                required=False,
            ),
        ],
        responses={200: "Get members of a organization"},
    )
    @action(
        detail=True, methods=["GET"], name="Get Organization users", url_name="users"
    )
    def users(self, request, pk=None):
        try:
            organization = Organization.objects.get(pk=pk)
        except Organization.DoesNotExist:
            return Response(
                {"message": "Organization not found"}, status=status.HTTP_404_NOT_FOUND
            )
        users = User.objects.filter(organization=organization)
        serializer = UserFetchSerializer(users, many=True)
        if "role" in request.query_params:
            role = request.query_params["role"]
            if role == "PROJECT_MANAGER":
                user_by_roles = users.filter(role="PROJECT_MANAGER")
                serializer = UserFetchSerializer(user_by_roles, many=True)
        return Response(serializer.data)

    @action(
        detail=True,
        methods=["GET"],
        name="List Projects in Organization",
        url_name="list_projects",
    )
    def list_projects(self, request, pk=None, *args, **kwargs):
        try:
            organization = Organization.objects.get(pk=pk)
            projects = Project.objects.filter(organization_id=organization)

            user = request.user
            if user.role == User.ORG_OWNER or user.is_superuser:
                serializer = ProjectSerializer(projects, many=True)
            else:
                projects_by_roles = []
                for project in projects:
                    if request.user in project.members.all():
                        projects_by_roles.append(project)
                if len(projects_by_roles) > 0:
                    serializer = ProjectSerializer(projects_by_roles, many=True)
                else:
                    return Response(
                        {
                            "message": "This user is not a member of any project in this organization."
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )
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

    @action(
        detail=True,
        methods=["GET"],
        name="List Projects in Organization",
        url_name="list_projects",
    )
    def list_org_tasks(self, request, pk=None, *args, **kwargs):
        try:
            organization = Organization.objects.get(pk=pk)
        except Organization.DoesNotExist:
            return Response(
                {"error": "Project does not exist"},
                status=status.HTTP_404_NOT_FOUND,
            )
        user = request.user
        if (
            organization.organization_owner == user
            or user.role == "ADMIN"
            or user.is_superuser
        ):
            projects = Project.objects.filter(organization_id=organization)
            videos = Video.objects.filter(project_id__in=projects)
            tasks = Task.objects.filter(video__in=videos)
        else:
            projects = Project.objects.filter(organization_id=organization).filter(
                managers__in=[user.id]
            )
            if len(projects) > 0:
                projects = Project.objects.filter(organization_id=organization).filter(
                    managers__in=[user.id]
                )
                videos = Video.objects.filter(project_id__in=projects)
                tasks_in_projects = Task.objects.filter(video__in=videos)
                assigned_tasks = Task.objects.filter(user=user)
                tasks = list(set(list(tasks_in_projects) + list(assigned_tasks)))
            else:
                tasks = Task.objects.filter(user=user)

        serializer = TaskSerializer(tasks, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @swagger_auto_schema(method="get", responses={200: "Success"})
    @action(
        detail=True,
        methods=["GET"],
        name="Get Report Users",
        url_name="get_report_users",
    )
    def get_report_users(self, request, pk=None, *args, **kwargs):
        try:
            org = Organization.objects.get(pk=pk)
        except Organization.DoesNotExist:
            return Response(
                {"message": "Organization not found"}, status=status.HTTP_404_NOT_FOUND
            )
        org_members = User.objects.filter(organization=pk).values("username", "email")
        user_statistics = (
            org_members.annotate(tasks_assigned_count=Count("task"))
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
        return Response(list(user_statistics), status=status.HTTP_200_OK)

    @swagger_auto_schema(method="get", responses={200: "Success"})
    @action(
        detail=True,
        methods=["GET"],
        name="Get Report Languages",
        url_name="get_report_langs",
    )
    def get_report_languages(self, request, pk=None, *args, **kwargs):
        try:
            org = Organization.objects.get(pk=pk)
        except Organization.DoesNotExist:
            return Response(
                {"message": "Organization not found"}, status=status.HTTP_404_NOT_FOUND
            )
        org_videos = Video.objects.filter(project_id__organization_id=pk)
        org_transcriptions = (
            Transcript.objects.filter(video__in=org_videos)
            .filter(status="TRANSCRIPTION_EDIT_COMPLETE")
            .values("language")
        )
        transcript_statistics = org_transcriptions.annotate(
            total_duration=Sum(F("video__duration"))
        )
        org_translations = (
            Translation.objects.filter(video__in=org_videos)
            .filter(status="TRANSLATION_EDIT_COMPLETE")
            .values(
                src_language=F("video__language"), tgt_language=F("target_language")
            )
        )
        translation_statistics = org_translations.annotate(
            transcripts_translated=Count("id")
        )
        res = {
            "transcript_stats": list(transcript_statistics),
            "translation_stats": list(translation_statistics),
        }
        return Response(res, status=status.HTTP_200_OK)

    @swagger_auto_schema(method="get", responses={200: "Success"})
    @action(
        detail=True,
        methods=["GET"],
        name="Get Report Projects",
        url_name="get_report_projects",
    )
    def get_report_projects(self, request, pk=None, *args, **kwargs):
        try:
            org = Organization.objects.get(pk=pk)
        except Organization.DoesNotExist:
            return Response(
                {"message": "Organization not found"}, status=status.HTTP_404_NOT_FOUND
            )
        org_projects = Project.objects.filter(organization_id=pk).values(
            "title", "managers__username"
        )
        project_stats = (
            org_projects.annotate(num_videos=Count("video"))
            .annotate(
                total_transcriptions=Sum(
                    "video__duration",
                    filter=Q(video__transcripts__status="TRANSCRIPTION_EDIT_COMPLETE"),
                )
            )
            .annotate(
                transcripts_translated=Count(
                    "video__translation_video",
                    filter=Q(
                        video__translation_video__status="TRANSLATION_EDIT_COMPLETE"
                    ),
                )
            )
        )
        return Response(list(project_stats), status=status.HTTP_200_OK)

    @swagger_auto_schema(method="get", responses={200: "Success"})
    @action(
        detail=False,
        methods=["GET"],
        name="Get Report Organizations",
        url_name="get_report_orgs",
    )
    def get_report_orgs(self, request, *args, **kwargs):
        org_stats = Organization.objects.all().values("title")
        org_stats = (
            org_stats.annotate(num_projects=Count("project", distinct=True))
            .annotate(num_videos=Count("project__video", distinct=True))
            .annotate(
                num_transcription_tasks=Count(
                    "project__video__tasks",
                    filter=Q(project__video__tasks__task_type="TRANSCRIPTION_EDIT"),
                )
            )
            .annotate(
                num_transcription_tasks_completed=Count(
                    "project__video__tasks",
                    filter=Q(project__video__tasks__task_type="TRANSCRIPTION_EDIT")
                    & Q(project__video__tasks__status="COMPLETE"),
                )
            )
            .annotate(
                num_translation_tasks=Count(
                    "project__video__tasks",
                    filter=Q(project__video__tasks__task_type="TRANSLATION_EDIT"),
                )
            )
            .annotate(
                num_translation_tasks_completed=Count(
                    "project__video__tasks",
                    filter=Q(project__video__tasks__task_type="TRANSLATION_EDIT")
                    & Q(project__video__tasks__status="COMPLETE"),
                )
            )
        )
        return Response(list(org_stats), status=status.HTTP_200_OK)
