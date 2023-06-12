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
from django.db.models import Q, Count, Avg, F, FloatField, BigIntegerField, Sum, Value
from django.db.models.functions import Cast, Concat
from datetime import timedelta, datetime
from video.models import Video
from transcript.models import Transcript
from translation.models import Translation
import json
from translation.metadata import LANGUAGE_CHOICES
from project.views import ProjectViewSet
from django.http import HttpRequest
from django.db.models import Q
from utils import *
import logging
import math
from django.db.models import Value
from django.db.models.functions import Concat


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
        default_voiceover_type = request.data.get("default_voiceover_type")
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
                default_voiceover_type=default_voiceover_type,
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
        default_voiceover_type = request.data.get("default_voiceover_type")
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
            "TRANSLATION_EDIT" in organization.default_task_types
            or "TRANSLATION_REVIEW" in organization.default_task_types
        ):
            default_target_languages = request.data.get("default_target_languages")
            if default_target_languages is None or len(default_target_languages) == 0:
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

        if default_voiceover_type is not None:
            organization.default_voiceover_type = default_voiceover_type
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
        users = User.objects.filter(organization=organization).filter(
            has_accepted_invite=True
        )
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
            projects = Project.objects.filter(organization_id=organization).order_by(
                "-created_at"
            )

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

    @swagger_auto_schema(
        method="get",
        manual_parameters=[
            openapi.Parameter(
                "limit",
                openapi.IN_QUERY,
                description=("Limit parameter"),
                type=openapi.TYPE_INTEGER,
                required=True,
            ),
            openapi.Parameter(
                "offset",
                openapi.IN_QUERY,
                description=("Offset parameter"),
                type=openapi.TYPE_INTEGER,
                required=True,
            ),
            openapi.Parameter(
                "filter",
                openapi.IN_QUERY,
                description=("Offset parameter"),
                type=openapi.TYPE_OBJECT,
                required=False,
            ),
            openapi.Parameter(
                "search",
                openapi.IN_QUERY,
                description=("Search parameter"),
                type=openapi.TYPE_OBJECT,
                required=False,
            ),
        ],
        responses={200: "List of org tasks"},
    )
    @action(
        detail=True,
        methods=["GET"],
        name="List Tasks in Organization",
        url_name="list_tasks",
    )
    def list_org_tasks(self, request, pk=None, *args, **kwargs):
        try:
            organization = Organization.objects.get(pk=pk)
            limit = int(request.query_params["limit"])
            offset = int(request.query_params["offset"])
            offset -= 1
            if "filter" in request.query_params:
                filter_dict = json.loads(request.query_params["filter"])

            if "search" in request.query_params:
                search_dict = json.loads(request.query_params["search"])

        except Organization.DoesNotExist:
            return Response(
                {"message": "Organization does not exist"},
                status=status.HTTP_404_NOT_FOUND,
            )

        user = request.user
        src_languages = set()
        target_languages = set()
        total_count = 0
        if (
            organization.organization_owner == user
            or user.role == "ADMIN"
            or user.is_superuser
        ):
            projects = Project.objects.filter(organization_id=organization)
            videos = Video.objects.filter(project_id__in=projects)
            # filter data based on search parameters
            videos = self.search_filter(videos, search_dict, filter_dict)

            all_tasks = Task.objects.filter(video__in=videos).order_by("-updated_at")

            if "description" in search_dict and len(search_dict["description"]):
                all_tasks = all_tasks.filter(
                    Q(description__contains=search_dict["description"])
                    | Q(description__contains=search_dict["description"])
                )
            if "assignee" in search_dict and len(search_dict["assignee"]):
                queryset = all_tasks.annotate(
                    search_name=Concat(
                        "user__first_name", Value(" "), "user__last_name"
                    )
                )
                all_tasks = queryset.filter(
                    search_name__icontains=search_dict["assignee"]
                )

            # filter data based on filter parameters
            all_tasks = self.filter_query(all_tasks, filter_dict)
            total_count = len(all_tasks)
            total_pages = math.ceil(total_count / int(limit))
            if offset > total_pages - 1:
                offset = 0
            start = offset * int(limit)
            end = start + int(limit) - 1
            tasks = all_tasks[start:end]
            tasks_serializer = TaskSerializer(tasks, many=True)
            tasks_list = json.loads(json.dumps(tasks_serializer.data))
            for task in tasks_list:
                src_languages.add(task["src_language_label"])
                target_languages.add(task["target_language_label"])
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
                if task["status"] == "COMPLETE":
                    buttons["Export"] = True
                    buttons["Preview"] = True
                    buttons["Update"] = False
                    buttons["Edit"] = False
                if task["status"] == "POST_PROCESS":
                    buttons["Update"] = True
                if task["user"]["email"] == request.user.email:
                    if task["status"] not in ["COMPLETE", "POST_PROCESS", "FAILED"]:
                        buttons["Edit"] = True
                    if (
                        task["status"] == "SELECTED_SOURCE"
                        and task["task_type"] != "VOICEOVER_EDIT"
                    ):
                        buttons["View"] = True
                task["buttons"] = buttons
        else:
            projects = (
                Project.objects.filter(organization_id=organization)
                .filter(managers__in=[user.id])
                .values_list("id", flat=True)
            )
            if len(projects) > 0:
                projects_only_members = (
                    Project.objects.filter(organization_id=organization)
                    .exclude(managers__in=[user.id])
                    .filter(members__in=[user.id])
                    .values_list("id", flat=True)
                )
                videos = Video.objects.filter(project_id__in=projects)
                # filter data based on search parameters
                videos = self.search_filter(videos, search_dict, filter_dict)

                all_tasks_in_projects = Task.objects.filter(video__in=videos).order_by(
                    "-updated_at"
                )
                if len(projects_only_members) > 0:
                    videos = Video.objects.filter(project_id__in=projects_only_members)

                    # filter data based on search parameters
                    videos = self.search_filter(videos, search_dict, filter_dict)

                    all_tasks_in_projects_assigned = (
                        Task.objects.filter(video__in=videos)
                        .filter(user=user)
                        .order_by("-updated_at")
                    )
                    all_tasks_in_projects = (
                        all_tasks_in_projects | all_tasks_in_projects_assigned
                    )

                if "assignee" in search_dict and len(search_dict["assignee"]):
                    queryset = all_tasks_in_projects.annotate(
                        search_name=Concat(
                            "user__first_name", Value(" "), "user__last_name"
                        )
                    )
                    all_tasks_in_projects = queryset.filter(
                        search_name__icontains=search_dict["assignee"]
                    )

                if "description" in search_dict and len(search_dict["description"]):
                    all_tasks_in_projects = all_tasks_in_projects.filter(
                        Q(description__contains=search_dict["description"])
                        | Q(description__contains=search_dict["description"])
                    )

                # filter data based on filter parameters
                all_tasks_in_projects = self.filter_query(
                    all_tasks_in_projects, filter_dict
                )
                total_count = len(all_tasks_in_projects)
                total_pages = math.ceil(total_count / int(limit))
                if offset > total_pages:
                    offset = 0
                start = offset * int(limit)
                end = start + int(limit)
                tasks_in_projects = all_tasks_in_projects[start:end]

                tasks_list = []
                for task_o in tasks_in_projects:
                    task_serializer = TaskSerializer(task_o)
                    task = json.loads(json.dumps(task_serializer.data))
                    src_languages.add(task["src_language_label"])
                    target_languages.add(task["target_language_label"])
                    buttons = {
                        "Edit": False,
                        "Preview": False,
                        "Export": False,
                        "Update": False,
                        "View": False,
                        "Delete": False,
                    }
                    if user in task_o.video.project_id.managers.all():
                        buttons["Update"] = True
                        buttons["Delete"] = True
                        if task["status"] == "COMPLETE":
                            buttons["Export"] = True
                            buttons["Preview"] = True
                            buttons["Update"] = False
                            buttons["Edit"] = False
                        if task["status"] == "POST_PROCESS":
                            buttons["Update"] = True
                    if task["user"]["email"] == request.user.email:
                        if task["status"] not in ["COMPLETE", "POST_PROCESS", "FAILED"]:
                            buttons["Edit"] = True
                        if (
                            task["status"] == "SELECTED_SOURCE"
                            and task["task_type"] != "VOICEOVER_EDIT"
                        ):
                            buttons["View"] = True
                    task["buttons"] = buttons
                    tasks_list.append(task)
            else:
                videos = Video.objects.all()
                # filter data based on search parameters
                videos = self.search_filter(videos, search_dict, filter_dict)

                all_tasks = (
                    Task.objects.filter(user=user)
                    .filter(video__in=videos)
                    .order_by("-updated_at")
                )

                if "assignee" in search_dict and len(search_dict["assignee"]):
                    queryset = all_tasks.annotate(
                        search_name=Concat(
                            "user__first_name", Value(" "), "user__last_name"
                        )
                    )
                    all_tasks = queryset.filter(
                        search_name__icontains=search_dict["assignee"]
                    )

                if "description" in search_dict and len(search_dict["description"]):
                    all_tasks = all_tasks.filter(
                        Q(description__contains=search_dict["description"])
                        | Q(description__contains=search_dict["description"])
                    )
                # filter data based on filter parameters
                all_tasks = self.filter_query(all_tasks, filter_dict)
                total_count = len(all_tasks)
                total_pages = math.ceil(total_count / int(limit))
                if offset > total_pages:
                    offset = 0
                start = offset * int(limit)
                end = start + int(limit)
                tasks = all_tasks[start:end]
                tasks_serializer = TaskSerializer(tasks, many=True)
                tasks_list = json.loads(json.dumps(tasks_serializer.data))
                for task in tasks_list:
                    src_languages.add(task["src_language_label"])
                    target_languages.add(task["target_language_label"])
                    buttons = {
                        "Edit": False,
                        "Preview": False,
                        "Export": False,
                        "Update": False,
                        "View": False,
                        "Delete": False,
                    }
                    if task["status"] == "COMPLETE":
                        buttons["Export"] = True
                        buttons["Preview"] = True
                    if task["user"]["email"] == request.user.email:
                        if task["status"] not in ["COMPLETE", "POST_PROCESS", "FAILED"]:
                            buttons["Edit"] = True
                        if (
                            task["status"] == "SELECTED_SOURCE"
                            and task["task_type"] != "VOICEOVER_EDIT"
                        ):
                            buttons["View"] = True
                    task["buttons"] = buttons
        target_languages_list = list(target_languages)
        if "-" in target_languages_list:
            target_languages_list.remove("-")
        return Response(
            {
                "total_count": total_count,
                "tasks_list": tasks_list,
                "src_languages_list": sorted(list(src_languages)),
                "target_languages_list": sorted(target_languages_list),
            },
            status=status.HTTP_200_OK,
        )

    def search_filter(self, videos, search_dict, filter_dict):
        if search_dict is not None:
            if "video_name" in search_dict:
                videos = videos.filter(Q(name__contains=search_dict["video_name"]))

        if "src_language" in filter_dict and len(filter_dict["src_language"]):
            src_lang_list = []
            for lang in filter_dict["src_language"]:
                lang_shortcode = get_language_label(lang)
                src_lang_list.append(lang_shortcode)
            if len(src_lang_list):
                videos = videos.filter(language__in=src_lang_list)

        return videos

    def filter_query(self, all_tasks, filter_dict):
        if "task_type" in filter_dict and len(filter_dict["task_type"]):
            all_tasks = all_tasks.filter(task_type__in=filter_dict["task_type"])
        if "target_language" in filter_dict and len(filter_dict["target_language"]):
            target_lang_list = []
            for lang in filter_dict["target_language"]:
                lang_shortcode = get_language_label(lang)
                target_lang_list.append(lang_shortcode)
            if len(target_lang_list):
                all_tasks = all_tasks.filter(target_language__in=target_lang_list)
        if "status" in filter_dict and len(filter_dict["status"]):
            all_tasks = all_tasks.filter(status__in=filter_dict["status"])

        return all_tasks

    def get_project_report_users(self, project_id, user):
        data = ProjectViewSet(detail=True)
        new_request = HttpRequest()
        new_request.user = user
        ret = data.get_report_users(new_request, project_id)
        return ret.data

    def get_project_report_languages(self, project_id, user):
        data = ProjectViewSet(detail=True)
        new_request = HttpRequest()
        new_request.user = user
        ret = data.get_report_languages(new_request, project_id)
        return ret.data

    @swagger_auto_schema(method="get", responses={200: "Success"})
    @action(
        detail=True,
        methods=["GET"],
        name="Get Report Users",
        url_name="get_report_users",
    )
    @is_particular_organization_owner
    def get_report_users(self, request, pk=None, *args, **kwargs):
        try:
            organization = Organization.objects.get(pk=pk)
        except Organization.DoesNotExist:
            return Response(
                {"message": "Organization not found"}, status=status.HTTP_404_NOT_FOUND
            )

        projects_in_org = Project.objects.filter(organization_id=organization).all()
        all_project_report = []
        if len(projects_in_org) > 0:
            for project in projects_in_org:
                project_report = self.get_project_report_users(project.id, request.user)
                for report in project_report:
                    report["project"] = {"value": project.title, "label": "Project"}
                    all_project_report.append(report)
        return Response(all_project_report, status=status.HTTP_200_OK)

    @swagger_auto_schema(method="get", responses={200: "Success"})
    @action(
        detail=True,
        methods=["GET"],
        name="Get Aggregated Report Users",
        url_name="get_aggregated_report_users",
    )
    @is_particular_organization_owner
    def get_aggregated_report_users(self, request, pk=None, *args, **kwargs):
        try:
            org = Organization.objects.get(pk=pk)
        except Organization.DoesNotExist:
            return Response(
                {"message": "Organization not found"}, status=status.HTTP_404_NOT_FOUND
            )
        org_members = (
            User.objects.filter(organization=pk)
            .filter(has_accepted_invite=True)
            .values(name=Concat("first_name", Value(" "), "last_name"), mail=F("email"))
            .order_by("mail")
        )
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
        user_data = []
        for elem in user_statistics:
            avg_time = (
                0
                if elem["average_completion_time"] is None
                else round(elem["average_completion_time"].total_seconds() / 3600, 3)
            )
            user_dict = {
                "name": {"value": elem["name"], "label": "Name", "viewColumns": False},
                "mail": {"value": elem["mail"], "label": "Email", "viewColumns": False},
                "tasks_assigned_count": {
                    "value": elem["tasks_assigned_count"],
                    "label": "Assigned Tasks",
                },
                "tasks_completed_count": {
                    "value": elem["tasks_completed_count"],
                    "label": "Completed Tasks",
                },
                "task_completion_percentage": {
                    "value": round(elem["task_completion_percentage"], 2),
                    "label": "Task Completion Index(%)",
                },
                "average_completion_time": {
                    "value": avg_time,
                    "label": "Avg. Completion Time (in seconds)",
                },
            }
            user_data.append(user_dict)
        return Response(user_data, status=status.HTTP_200_OK)

    def format_completion_time(self, completion_time):
        if completion_time < 60 * 60:
            full_time = (
                str(int(completion_time // 60))
                + "m "
                + str(int(completion_time % 60))
                + "s"
            )
        elif completion_time >= 60 * 60 and completion_time < 24 * 60 * 60:
            full_time = (
                str(int(completion_time // (60 * 60)))
                + "h "
                + str(int((completion_time % (60 * 60)) // 60))
                + "m"
            )
        elif completion_time >= 24 * 60 * 60 and completion_time < 30 * 24 * 60 * 60:
            full_time = (
                str(int(completion_time // (24 * 60 * 60)))
                + "d "
                + str(int((completion_time % (24 * 60 * 60)) // (60 * 60)))
                + "h"
            )
        elif (
            completion_time >= 30 * 24 * 60 * 60
            and completion_time < 12 * 30 * 24 * 60 * 60
        ):
            full_time = (
                str(int(completion_time // (30 * 24 * 60 * 60)))
                + "m "
                + str(int((completion_time % (30 * 24 * 60 * 60)) // (24 * 60 * 60)))
                + "d"
            )
        else:
            full_time = (
                str(int(completion_time // (12 * 30 * 24 * 60 * 60)))
                + "y "
                + str(
                    int(
                        (completion_time % (12 * 30 * 24 * 60 * 60))
                        // (30 * 24 * 60 * 60)
                    )
                )
                + "m"
            )
        return full_time

    @swagger_auto_schema(method="get", responses={200: "Success"})
    @action(
        detail=True,
        methods=["GET"],
        name="Get Task report",
        url_name="get_tasks_report",
    )
    @is_particular_organization_owner
    def get_tasks_report(self, request, pk=None, *args, **kwargs):
        try:
            org = Organization.objects.get(pk=pk)
        except Organization.DoesNotExist:
            return Response(
                {"message": "Organization not found"}, status=status.HTTP_404_NOT_FOUND
            )

        org_videos = Video.objects.filter(project_id__organization_id=pk)
        task_orgs = Task.objects.filter(video__in=org_videos)
        tasks_list = []
        for task in task_orgs:
            if task.description is not None:
                description = task.description
            elif task.video.description is not None:
                description = task.video.description
            else:
                description = None

            if "COMPLETE" in task.status:
                datetime_str = task.updated_at
                updated_at_str = task.updated_at.strftime("%m-%d-%Y %H:%M:%S.%f")
                updated_at_datetime_object = datetime.strptime(
                    updated_at_str, "%m-%d-%Y %H:%M:%S.%f"
                )
                compare_with = "05-04-2023 17:00:00.000"
                compare_with_datetime_object = datetime.strptime(
                    compare_with, "%m-%d-%Y %H:%M:%S.%f"
                )

                if updated_at_datetime_object < compare_with_datetime_object:
                    time_spent = float(
                        "{:.2f}".format(
                            (task.updated_at - task.created_at).total_seconds()
                        )
                    )
                else:
                    time_spent = task.time_spent
                completion_time = self.format_completion_time(time_spent)
            else:
                completion_time = None

            tasks_list.append(
                {
                    "project_name": {
                        "value": task.video.project_id.title,
                        "label": "Project Name",
                        "viewColumns": False,
                    },
                    "video_name": {
                        "value": task.video.name, 
                        "label": "Video Name",
                        "viewColumns": False,
                    },
                    "video_url": {
                        "value": task.video.url,
                        "label": "Video URL",
                        "display": "exclude",
                    },
                    "duration": {
                        "value": str(task.video.duration),
                        "label": "Duration",
                    },
                    "task_type": {
                        "value": task.get_task_type_label,
                        "label": "Task Type",
                        "viewColumns": False
                    },
                    "task_description": {
                        "value": description,
                        "label": "Task Description",
                        "display": "exclude",
                    },
                    "source_language": {
                        "value": task.get_src_language_label,
                        "label": "Source Langauge",
                    },
                    "target_language": {
                        "value": task.get_target_language_label,
                        "label": "Target Langauge",
                    },
                    "assignee": {
                        "value": task.user.email, 
                        "label": "Assignee",
                    },
                    "status": {
                        "value": task.get_task_status_label, 
                        "label": "Status"
                    },
                    "completion_time": {
                        "value": completion_time,
                        "label": "Completion Time",
                        "display": "exclude",
                    },
                }
            )
        return Response(tasks_list, status=status.HTTP_200_OK)

    @swagger_auto_schema(method="get", responses={200: "Success"})
    @action(
        detail=True,
        methods=["GET"],
        name="Get Report Languages",
        url_name="get_report_langs",
    )
    @is_particular_organization_owner
    def get_report_languages(self, request, pk=None, *args, **kwargs):
        try:
            org = Organization.objects.get(pk=pk)
        except Organization.DoesNotExist:
            return Response(
                {"message": "Organization not found"}, status=status.HTTP_404_NOT_FOUND
            )
        projects_in_org = Project.objects.filter(organization_id=org).all()
        all_project_report = []
        if len(projects_in_org) > 0:
            for project in projects_in_org:
                project_report = self.get_project_report_languages(
                    project.id, request.user
                )
                for keys, values in project_report.items():
                    for report in values:
                        report["project"] = {"value": project.title, "label": "Project", "viewColumns": False}
                all_project_report.append(project_report)

        aggregated_project_report = {"transcript_stats": [], "translation_stats": []}
        for project_report in all_project_report:
            if type(project_report) == dict:
                if (
                    "transcript_stats" in project_report.keys()
                    and len(project_report["transcript_stats"]) > 0
                ):

                    for i in range(len(project_report["transcript_stats"])):
                        new_stats = dict(
                            reversed(
                                list(project_report["transcript_stats"][i].items())
                            )
                        )
                        project_report["transcript_stats"][i] = new_stats
                    dict(reversed(list(report.items())))
                    aggregated_project_report["transcript_stats"].extend(
                        project_report["transcript_stats"]
                    )
                if (
                    "translation_stats" in project_report.keys()
                    and len(project_report["translation_stats"]) > 0
                ):
                    for i in range(len(project_report["translation_stats"])):
                        new_stats = dict(
                            reversed(
                                list(project_report["translation_stats"][i].items())
                            )
                        )
                        project_report["translation_stats"][i] = new_stats
                    aggregated_project_report["translation_stats"].extend(
                        project_report["translation_stats"]
                    )
        return Response(aggregated_project_report, status=status.HTTP_200_OK)

    @swagger_auto_schema(method="get", responses={200: "Success"})
    @action(
        detail=True,
        methods=["GET"],
        name="Get Aggregated Report Languages",
        url_name="get_aggregated_report_langs",
    )
    @is_particular_organization_owner
    def get_aggregated_report_languages(self, request, pk=None, *args, **kwargs):
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
        ).order_by("-total_duration")
        org_translations = (
            Translation.objects.filter(video__in=org_videos)
            .filter(status="TRANSLATION_EDIT_COMPLETE")
            .values(
                src_language=F("video__language"), tgt_language=F("target_language")
            )
        )
        translation_statistics = (
            org_translations.annotate(transcripts_translated=Count("id"))
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
                    "viewColumns": False,
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
                    "viewColumns": False,
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

    @swagger_auto_schema(method="get", responses={200: "Success"})
    @action(
        detail=True,
        methods=["GET"],
        name="Get Report Projects",
        url_name="get_report_projects",
    )
    @is_particular_organization_owner
    def get_report_projects(self, request, pk=None, *args, **kwargs):
        try:
            org = Organization.objects.get(pk=pk)
        except Organization.DoesNotExist:
            return Response(
                {"message": "Organization not found"}, status=status.HTTP_404_NOT_FOUND
            )
        org_projects = (
            Project.objects.filter(organization_id=pk)
            .values("title", "id")
            .order_by("id")
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
                total_translations=Sum(
                    "video__duration",
                    filter=Q(
                        video__translation_video__status="TRANSLATION_EDIT_COMPLETE"
                    ),
                )
            )
        )

        project_data = []
        for elem in project_stats:
            manager_names = Project.objects.get(pk=elem["id"]).managers.all()
            manager_list = []
            for manager_name in manager_names:
                manager_list.append(
                    manager_name.first_name + " " + manager_name.last_name
                )
            transcript_duration = (
                None
                if elem["total_transcriptions"] is None
                else round(elem["total_transcriptions"].total_seconds() / 3600, 3)
            )
            translation_duration = (
                None
                if elem["total_translations"] is None
                else round(elem["total_translations"].total_seconds() / 3600, 3)
            )
            project_dict = {
                "title": {"value": elem["title"], "label": "Title", "viewColumns": False},
                "managers__username": {"value": manager_list, "label": "Managers", "viewColumns": False},
                "num_videos": {"value": elem["num_videos"], "label": "Video count"},
                "total_transcriptions": {
                    "value": transcript_duration,
                    "label": "Transcripted Duration (Hours)",
                },
                "total_translations": {
                    "value": translation_duration,
                    "label": "Translated Duration (Hours)",
                },
            }
            project_data.append(project_dict)

        return Response(project_data, status=status.HTTP_200_OK)

    @swagger_auto_schema(method="get", responses={200: "Success"})
    @action(
        detail=False,
        methods=["GET"],
        name="Get Report Organizations",
        url_name="get_report_orgs",
    )
    @is_admin
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
        org_data = []
        for elem in org_stats:
            org_dict = {
                "title": {"value": elem["title"], "label": "Title", "viewColumns": False},
                "num_projects": {
                    "value": elem["num_projects"],
                    "label": "Project count",
                },
                "num_videos": {"value": elem["num_videos"], "label": "Video count"},
                "num_transcription_tasks": {
                    "value": elem["num_transcription_tasks"],
                    "label": "Assigned Transcription Tasks",
                },
                "num_transcription_tasks_completed": {
                    "value": elem["num_transcription_tasks_completed"],
                    "label": "Completed Transcription Tasks",
                },
                "num_translation_tasks": {
                    "value": elem["num_translation_tasks"],
                    "label": "Assigned Translation tasks",
                },
                "num_translation_tasks_completed": {
                    "value": elem["num_translation_tasks_completed"],
                    "label": "Completed Translation tasks",
                },
            }
            org_data.append(org_dict)
        return Response(org_data, status=status.HTTP_200_OK)

    @swagger_auto_schema(
        method="post",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                "org_id": openapi.Schema(
                    type=openapi.TYPE_INTEGER, format="org_id", description="Org Id"
                ),
                "enable_upload": openapi.Schema(
                    type=openapi.TYPE_BOOLEAN,
                    format="boolean",
                    description="Enable CSV Upload",
                ),
            },
            required=["org_id"],
        ),
        responses={
            200: "CSV upload enabled.",
            403: "Please enter a valid organization!",
        },
    )
    @action(
        detail=False,
        methods=["post"],
        url_path="enable_org_csv_upload",
        url_name="enable_org_csv_upload",
    )
    def enable_org_csv_upload(self, request):
        """
        Update the mail enable service for any user
        """
        requested_id = request.data.get("org_id")
        enable_upload = request.data.get("enable_upload")

        if enable_upload == True or enable_upload == False:
            pass
        else:
            return Response(
                {
                    "message": "please enter valid  input(True/False) for enable_upload field"
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            org = Organization.objects.get(id=requested_id)
        except Organization.DoesNotExist:
            return Response(
                {"message": "Organization not found"}, status=status.HTTP_404_NOT_FOUND
            )

        org.enable_upload = enable_upload
        org.save()
        return Response(
            {"message": "CSV Upload is enabled."},
            status=status.HTTP_200_OK,
        )
