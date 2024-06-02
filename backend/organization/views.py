from rest_framework import viewsets
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import action
from rest_framework import status
from rest_framework.views import APIView
from users.serializers import UserFetchSerializer
from users.models import User
from .models import Organization, OnboardOrganisationAccount
from .serializers import OrganizationSerializer, OnboardingOrgAccountSerializer
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
from translation.metadata import TRANSLATION_LANGUAGE_CHOICES
from django.http import HttpRequest
from django.db.models import Q
import logging
import math
from django.db.models import Value
from django.db.models.functions import Concat
from project.utils import *
from .tasks import *
from .utils import *
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
import ast


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
        new_org_owner_email = request.data.get("new_org_owner_email")
        default_transcript_type = request.data.get("default_transcript_type")
        default_translation_type = request.data.get("default_translation_type")
        default_voiceover_type = request.data.get("default_voiceover_type")
        default_task_types = request.data.get("default_task_types")
        default_target_languages = None
        first_word = title.split()[0]
        password = f"demo@{first_word}"
        u_name = f"ORG_OWNER_{first_word}"
        if title is None:
            return Response(
                {
                    "message": "missing param : title (Org name)"
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        
        if email_domain_name is None:
            return Response(
                {
                    "message": "missing param : email_domain_name (Org email domain)"
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        
        if not (organization_owner or new_org_owner_email):
            return Response(
                {
                    "message": "missing param : organization_owner or new_org_owner_email"
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        if Organization.objects.filter(title=title).exists():
            return Response({"message": "Organization already exists"}, status=status.HTTP_400_BAD_REQUEST)
        if Organization.objects.filter(email_domain_name = email_domain_name ).exists():
            return Response({"message": "Email Domain Name already exists"}, status=status.HTTP_400_BAD_REQUEST)
        if organization_owner:
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
        elif new_org_owner_email:
            try:
                validate_email(new_org_owner_email)
            except ValidationError:
                return Response(
                    {"message": "Invalid email address for organization owner"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            # Create a new user with org_owner role
            try:
                organization_owner = User.objects.create_user(
                    username=u_name,
                    email=new_org_owner_email,
                    password=password,
                    has_accepted_invite=True,
                    role=User.ORG_OWNER,
                    first_name="Organization Owner",
                    last_name=title
                )
                # org_owner_id = organization_owner.id
            except Exception:
                return Response(
                    {"message": "Organization owner with the email already exists"},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
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
            print()
        except:
            return Response(
                {"message": "Organization can't be created"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        organization_owner.organization = organization
        organization_owner.save()
        email_subject = f'Welcome to {app_name} Application'
        if request.data.get("organization_owner"):
            email_message = f'Hi,\n\nYou have been registered to {app_name} Application as Organization Owner of {title}.\n\nBest regards,\nThe {app_name} Team'
            send_mail(email_subject, email_message, settings.DEFAULT_FROM_EMAIL, [new_org_owner_email])
        else:
            email_message = f'Hi,\n\nYou have been registered to {app_name} Application as Organization Owner of {title}.\n\nEmail_ID: {new_org_owner_email}\n\nPassword: {password}\n\nBest regards,\nThe {app_name} Team'
            send_mail(email_subject, email_message, settings.DEFAULT_FROM_EMAIL, [new_org_owner_email])
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
                "sort_by",
                openapi.IN_QUERY,
                description=("Sorting parameter"),
                type=openapi.TYPE_STRING,
                required=False,
            ),
            openapi.Parameter(
                "reverse",
                openapi.IN_QUERY,
                description=("Orderby parameter"),
                type=openapi.TYPE_BOOLEAN,
                required=False,
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
            sort_by = request.query_params.get("sort_by", "updated_at")
            reverse = request.query_params.get("reverse", "True")
            reverse = reverse.lower() == "true"
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
            videos = task_search_filter(videos, search_dict, filter_dict)

            if reverse == True:
                sort_by = "-" + sort_by
            all_tasks = Task.objects.filter(video_id__in=videos).order_by(sort_by)

            all_tasks = task_search_by_task_id(all_tasks, search_dict)
            all_tasks = task_search_by_description(all_tasks, search_dict)
            all_tasks = task_search_by_assignee(all_tasks, search_dict)
            all_tasks = search_active_task(all_tasks, search_dict)

            # filter data based on filter parameters
            all_tasks = task_filter_query(all_tasks, filter_dict)
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
                    "Info": False,
                    "Reopen": False,
                    "Regenerate": False,
                }
                buttons["Update"] = True
                buttons["Delete"] = True
                if task["status"] == "COMPLETE":
                    buttons["Export"] = True
                    buttons["Preview"] = True
                    buttons["Update"] = False
                    buttons["Edit"] = False
                    if "TRANSLATION" in task["task_type"]:
                        buttons["Reopen"] = True
                        if data["task_type"] == "TRANSLATION_VOICEOVER_EDIT":
                            buttons["Reopen"] = False
                if task["status"] == "POST_PROCESS":
                    buttons["Update"] = True
                if task["status"] == "FAILED":
                    buttons["Info"] = True
                    if task["is_active"] == True:
                        buttons["Reopen"] = True
                        if data["task_type"] == "TRANSLATION_VOICEOVER_EDIT":
                            buttons["Reopen"] = False
                    else:
                        buttons["Regenerate"] = True
                if task["status"] == "REOPEN":
                    buttons["Info"] = True
                if task["status"] == "INPROGRESS":
                    buttons["Preview"] = True
                if task["task_type"] == "VOICEOVER_EDIT":
                    buttons["Preview"] = False
                    buttons["Info"] = False
                    if task["status"] == "FAILED":
                        buttons["Reopen"] = False
                        buttons["Regenerate"] = False
                if task["user"]["email"] == request.user.email:
                    if task["status"] not in ["COMPLETE", "POST_PROCESS", "FAILED"]:
                        buttons["Edit"] = True
                    if (
                        task["status"] == "SELECTED_SOURCE"
                        and task["task_type"] != "VOICEOVER_EDIT"
                    ):
                        buttons["View"] = False
                        if task["task_type"] == "TRANSCRIPTION_EDIT" and task["source_type"] == "Manually Uploaded":
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
                videos = task_search_filter(videos, search_dict, filter_dict)

                if reverse == True:
                    sort_by = "-" + sort_by
                all_tasks_in_projects = Task.objects.filter(video__in=videos).order_by(
                    sort_by
                )
                if len(projects_only_members) > 0:
                    videos = Video.objects.filter(project_id__in=projects_only_members)

                    # filter data based on search parameters
                    videos = task_search_filter(videos, search_dict, filter_dict)

                    all_tasks_in_projects_assigned = (
                        Task.objects.filter(video__in=videos)
                        .filter(user=user)
                        .order_by("-updated_at")
                    )
                    all_tasks_in_projects = (
                        all_tasks_in_projects | all_tasks_in_projects_assigned
                    )

                all_tasks_in_projects = task_search_by_task_id(
                    all_tasks_in_projects, search_dict
                )
                all_tasks_in_projects = task_search_by_description(
                    all_tasks_in_projects, search_dict
                )
                all_tasks_in_projects = task_search_by_assignee(
                    all_tasks_in_projects, search_dict
                )

                # filter data based on filter parameters
                all_tasks_in_projects = task_filter_query(
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
                        "Info": False,
                        "Reopen": False,
                        "Regenerate": False,
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
                        if task["status"] == "FAILED":
                            buttons["Info"] = True
                            if task["is_active"] == False:
                                buttons["Regenerate"] = True
                            else:
                                buttons["Reopen"] = True
                        if task["status"] == "REOPEN":
                            buttons["Info"] = True
                        if task["status"] == "INPROGRESS":
                            buttons["Preview"] = True
                        if task["task_type"] == "VOICEOVER_EDIT":
                            buttons["Preview"] = False
                            buttons["Info"] = False
                            if task["status"] == "FAILED":
                                buttons["Reopen"] = False
                                buttons["Regenerate"] = False
                    if task["user"]["email"] == request.user.email:
                        if task["status"] not in ["COMPLETE", "POST_PROCESS", "FAILED"]:
                            buttons["Edit"] = True
                        if (
                            task["status"] == "SELECTED_SOURCE"
                            and task["task_type"] != "VOICEOVER_EDIT"
                        ):
                            buttons["View"] = False
                            if task["task_type"] == "TRANSCRIPTION_EDIT" and task["source_type"] == "Manually Uploaded":
                                buttons["View"] = True
                    task["buttons"] = buttons
                    tasks_list.append(task)
            else:
                videos = Video.objects.all()
                # filter data based on search parameters
                videos = task_search_filter(videos, search_dict, filter_dict)
                if reverse == True:
                    sort_by = "-" + sort_by
                all_tasks = (
                    Task.objects.filter(user=user)
                    .filter(video__in=videos)
                    .order_by(sort_by)
                )

                all_tasks = task_search_by_task_id(all_tasks, search_dict)
                all_tasks = task_search_by_description(all_tasks, search_dict)
                all_tasks = task_search_by_assignee(all_tasks, search_dict)

                # filter data based on filter parameters
                all_tasks = task_filter_query(all_tasks, filter_dict)
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
                        "Info": False,
                        "Reopen": False,
                        "Regenerate": False,
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
                            buttons["View"] = False
                            if task["task_type"] == "TRANSCRIPTION_EDIT" and task["source_type"] == "Manually Uploaded":
                                buttons["View"] = True
                        if task["status"] == "FAILED":
                            buttons["Info"] = True
                        if task["status"] == "INPROGRESS":
                            buttons["Preview"] = True
                        if task["task_type"] == "VOICEOVER_EDIT":
                            buttons["Preview"] = False
                            buttons["Info"] = False
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

    @swagger_auto_schema(method="get", responses={200: "Success"})
    @action(
        detail=True,
        methods=["GET"],
        name="Send Report Users Email",
        url_name="send_users_report_email",
    )
    @is_particular_organization_owner
    def send_users_report_email(self, request, pk=None, *args, **kwargs):
        try:
            organization = Organization.objects.get(pk=pk)
        except Organization.DoesNotExist:
            return Response(
                {"message": "Organization not found"}, status=status.HTTP_404_NOT_FOUND
            )
        send_email_with_users_report.delay(organization.id, request.user.id)
        return Response(
            {"message": "Reports will be emailed."}, status=status.HTTP_200_OK
        )

    @swagger_auto_schema(method="get", responses={200: "Success"})
    @action(
        detail=True,
        methods=["GET"],
        name="Send Report Tasks Email",
        url_name="send_tasks_report_email",
    )
    @is_particular_organization_owner
    def send_tasks_report_email(self, request, pk=None, *args, **kwargs):
        try:
            org = Organization.objects.get(pk=pk)
        except Organization.DoesNotExist:
            return Response(
                {"message": "Organization not found"}, status=status.HTTP_404_NOT_FOUND
            )
        send_email_with_tasks_report.delay(org.id, request.user.id)
        return Response(
            {"message": "Reports will be emailed."}, status=status.HTTP_200_OK
        )

    @swagger_auto_schema(method="get", responses={200: "Success"})
    @action(
        detail=True,
        methods=["GET"],
        name="Send Report Projects Email",
        url_name="send_projects_report_email",
    )
    @is_particular_organization_owner
    def send_projects_report_email(self, request, pk=None, *args, **kwargs):
        try:
            org = Organization.objects.get(pk=pk)
        except Organization.DoesNotExist:
            return Response(
                {"message": "Organization not found"}, status=status.HTTP_404_NOT_FOUND
            )
        send_email_with_projects_report.delay(org.id, request.user.id)
        return Response(
            {"message": "Reports will be emailed."}, status=status.HTTP_200_OK
        )

    @swagger_auto_schema(method="get", responses={200: "Success"})
    @action(
        detail=True,
        methods=["GET"],
        name="Send Report Languages Email",
        url_name="Send_languages_report_email",
    )
    @is_particular_organization_owner
    def send_languages_report_email(self, request, pk=None, *args, **kwargs):
        try:
            organization = Organization.objects.get(pk=pk)
        except Organization.DoesNotExist:
            return Response(
                {"message": "Organization not found"}, status=status.HTTP_404_NOT_FOUND
            )
        send_email_with_languages_report.delay(organization.id, request.user.id)
        return Response(
            {"message": "Reports will be emailed."}, status=status.HTTP_200_OK
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
        ],
        responses={200: "Report of organization languages."},
    )
    @action(
        detail=True,
        methods=["GET"],
        name="Get Report Users",
        url_name="get_report_users",
    )
    @is_particular_organization_owner
    def get_report_users(self, request, pk=None, *args, **kwargs):
        limit = int(request.query_params["limit"])
        offset = int(request.query_params["offset"])

        try:
            organization = Organization.objects.get(pk=pk)
        except Organization.DoesNotExist:
            return Response(
                {"message": "Organization not found"}, status=status.HTTP_404_NOT_FOUND
            )

        projects_in_org = Project.objects.filter(organization_id=organization).all()
        project_users_data = []
        all_project_report = []
        if len(projects_in_org) > 0:
            for project in projects_in_org:
                project_members = (
                    User.objects.filter(projects__pk=project.id)
                    .filter(has_accepted_invite=True)
                    .values(
                        name=Concat("first_name", Value(" "), "last_name"),
                        mail=F("email"),
                    )
                    .order_by("mail")
                )

                members_project = project_members.annotate(
                    tasks_assigned_count=Count(
                        "task", filter=Q(task__video__project_id=project.id)
                    )
                ).exclude(tasks_assigned_count=0)
                if len(members_project) != 0:
                    project_users_data.append((project.id, len(members_project)))

            total_count = sum(i[1] for i in project_users_data)
            user_data = paginate_reports(project_users_data, limit)

            for project_report_user in user_data[offset]:
                project_report, _ = get_reports_for_users(
                    project_report_user[0],
                    project_report_user[1],
                    project_report_user[2] + 1,
                )
                for report in project_report:
                    report["project"] = {
                        "value": Project.objects.get(pk=project_report_user[0]).title,
                        "label": "Project",
                    }
                    all_project_report.append(report)
        return Response(
            {"reports": all_project_report, "total_count": total_count},
            status=status.HTTP_200_OK,
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
        ],
        responses={200: "Report of organization languages."},
    )
    @action(
        detail=True,
        methods=["GET"],
        name="Get Aggregated Report Users",
        url_name="get_aggregated_report_users",
    )
    @is_particular_organization_owner
    def get_aggregated_report_users(self, request, pk=None, *args, **kwargs):
        limit = int(request.query_params["limit"])
        offset = int(request.query_params["offset"])
        try:
            org = Organization.objects.get(pk=pk)
        except Organization.DoesNotExist:
            return Response(
                {"message": "Organization not found"}, status=status.HTTP_404_NOT_FOUND
            )
        offset = offset - 1
        start = offset * int(limit)
        end = start + int(limit)
        org_members = (
            User.objects.filter(organization=pk)
            .filter(has_accepted_invite=True)
            .values(name=Concat("first_name", Value(" "), "last_name"), mail=F("email"))
            .order_by("mail")
        )
        all_user_statistics = (
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
                    Case(
                        When(
                            (
                                Q(task__status="COMPLETE")
                                & Q(task__updated_at__lt=(datetime(2023, 4, 5, 17, 0, 0)))
                            ),
                            then=(
                                Extract(
                                    F("task__updated_at") - F("task__created_at"),
                                    "epoch",
                                )
                            ),
                        ),
                        When(
                            (
                                Q(task__status="COMPLETE")
                                & Q(task__updated_at__gte=(datetime(2023, 4, 5, 17, 0, 0)))
                            ),
                            then=F("task__time_spent"),
                        ),
                        default=0,
                        output_field=IntegerField(),
                    ),
                    filter=Q(task__status="COMPLETE"),
                )
            )
            .exclude(tasks_assigned_count=0)
        )
        user_statistics = all_user_statistics[start:end]
        total_count = len(all_user_statistics)

        user_data = []
        word_count_idx = 0
        for elem in user_statistics:
            transcript_word_count = User.objects.filter(
                transcript__video__project_id__organization_id__id=pk,
                transcript__status="TRANSCRIPTION_EDIT_COMPLETE",
                transcript__task__user__email=elem["mail"],
            ).aggregate(
                transcript_word_count=Sum(
                    Cast("transcript__payload__word_count", FloatField())
                )
            )

            transcript_result = (
                transcript_word_count["transcript_word_count"]
                if transcript_word_count["transcript_word_count"] is not None
                else 0.0
            )

            translation_word_count = User.objects.filter(
                translation__video__project_id__organization_id__id=pk,
                translation__status="TRANSLATION_EDIT_COMPLETE",
                translation__task__user__email=elem["mail"],
            ).aggregate(
                translation_word_count=Sum(
                    Cast("translation__payload__word_count", FloatField())
                )
            )

            translation_result = (
                translation_word_count["translation_word_count"]
                if translation_word_count["translation_word_count"] is not None
                else 0.0
            )
            elem["word_count_translation"] = int(translation_result)
            elem["word_count_transcript"] = int(transcript_result)

        user_data = []
        for elem in user_statistics:
            avg_time = (
                0
                if elem["average_completion_time"] is None
                else round(elem["average_completion_time"] / 3600, 3)
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
                "tasks_completion_perc": {
                    "value": round(elem["task_completion_percentage"], 2),
                    "label": "Task Completion Index(%)",
                },
                "avg_comp_time": {
                    "value": float("{:.2f}".format(avg_time)),
                    "label": "Avg. Completion Time (Hours)",
                },
                "word_count": {
                    "value": elem["word_count_translation"]
                    + elem["word_count_transcript"],
                    "label": "Word count",
                },
                "project": {
                    "value": "",
                    "label": "Project",
                },
            }
            user_data.append(user_dict)
        return Response(
            {"reports": user_data, "total_count": total_count},
            status=status.HTTP_200_OK,
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
        ],
        responses={200: "Report of organization tasks."},
    )
    @action(
        detail=True,
        methods=["GET"],
        name="Get Task report",
        url_name="get_tasks_report",
    )
    @is_particular_organization_owner
    def get_tasks_report(self, request, pk=None, *args, **kwargs):
        limit = int(request.query_params["limit"])
        offset = int(request.query_params["offset"])

        try:
            org = Organization.objects.get(pk=pk)
        except Organization.DoesNotExist:
            return Response(
                {"message": "Organization not found"}, status=status.HTTP_404_NOT_FOUND
            )
        tasks_list, total_count = get_org_report_tasks(pk, request.user, limit, offset)
        return Response(
            {"reports": tasks_list, "total_count": total_count},
            status=status.HTTP_200_OK,
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
                "task_type",
                openapi.IN_QUERY,
                description=("Task Type"),
                type=openapi.TYPE_STRING,
                required=True,
            ),
        ],
        responses={200: "Report of organization languages."},
    )
    @action(
        detail=True,
        methods=["GET"],
        name="Get Report Languages",
        url_name="get_report_langs",
    )
    @is_particular_organization_owner
    def get_report_languages(self, request, pk=None, *args, **kwargs):
        limit = int(request.query_params["limit"])
        offset = int(request.query_params["offset"])
        task_type = request.query_params["task_type"]
        try:
            org = Organization.objects.get(pk=pk)
        except Organization.DoesNotExist:
            return Response(
                {"message": "Organization not found"}, status=status.HTTP_404_NOT_FOUND
            )
        aggregated_project_report = get_org_report_languages(pk, request.user)
        start_offset = (int(offset) - 1) * int(limit)
        end_offset = start_offset + int(limit)
        return Response(
            {
                "reports": aggregated_project_report[task_type][
                    start_offset:end_offset
                ],
                "total_count": len(aggregated_project_report[task_type]),
            },
            status=status.HTTP_200_OK,
        )

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
                    "value": dict(TRANSLATION_LANGUAGE_CHOICES)[elem["language"]],
                    "label": "Source Language",
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
                    "value": dict(TRANSLATION_LANGUAGE_CHOICES)[elem["src_language"]],
                    "label": "Source Language",
                },
                "tgt_language": {
                    "value": dict(TRANSLATION_LANGUAGE_CHOICES)[elem["tgt_language"]],
                    "label": "Target Language",
                },
                "translation_duration": {
                    "value": round(
                        elem["translation_duration"].total_seconds() / 3600, 3
                    ),
                    "label": "Duration (Hours)",
                    "viewColumns": False,
                },
                "transcripts_translated": {
                    "value": elem["transcripts_translated"],
                    "label": "Tasks Count",
                },
            }
            translation_data.append(translation_dict)
        res = {
            "transcript_stats": transcript_data,
            "translation_stats": translation_data,
        }
        return Response(res, status=status.HTTP_200_OK)

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
        ],
        responses={200: "Report of organization projects."},
    )
    @action(
        detail=True,
        methods=["GET"],
        name="Get Report Projects",
        url_name="get_report_projects",
    )
    @is_particular_organization_owner
    def get_report_projects(self, request, pk=None, *args, **kwargs):
        limit = int(request.query_params["limit"])
        offset = int(request.query_params["offset"])

        try:
            org = Organization.objects.get(pk=pk)
        except Organization.DoesNotExist:
            return Response(
                {"message": "Organization not found"}, status=status.HTTP_404_NOT_FOUND
            )
        project_data, total_count = get_org_report_projects(
            pk, request.user, limit, offset
        )
        return Response(
            {"reports": project_data, "total_count": total_count},
            status=status.HTTP_200_OK,
        )

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
                "title": {
                    "value": elem["title"],
                    "label": "Title",
                    "viewColumns": False,
                },
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

class OnboardingOrgAccountApiView(APIView):
    def get(self, request, pk=None, format=None):
        if request.user.email not in ast.literal_eval(point_of_contacts):
            return Response(
                    {"message":"You are not authorized to access this data"},
                    status=status.HTTP_403_FORBIDDEN,
                )
        id=pk
        if id is not None:
            try:
                onboarding_request = OnboardOrganisationAccount.objects.get(id=id)
            except OnboardOrganisationAccount.DoesNotExist:
                return Response(
                    {"message": "Onboard request not found"}, status=status.HTTP_404_NOT_FOUND
                )
            serialized_data = OnboardingOrgAccountSerializer(onboarding_request)
            return Response(
                    serialized_data.data,
                    status=status.HTTP_200_OK,
            )
        else:
            onboarding_requests = OnboardOrganisationAccount.objects.all()
            onboarding_requests= list(onboarding_requests)
            serialized_data = OnboardingOrgAccountSerializer(onboarding_requests, many=True)
            return Response(
                serialized_data.data,
                status=status.HTTP_200_OK,
            )

    
    def patch(self, request, pk=None, *args, **kwargs):
        if request.user.email not in ast.literal_eval(point_of_contacts):
            return Response(
                {"message":"You are not authorized to modify this data"},
                status=status.HTTP_403_FORBIDDEN,
            )
        id=pk
        orgname = request.data.get("orgname")
        org_portal = request.data.get("org_portal")
        email_domain_name = request.data.get("email_domain_name")
        org_type = request.data.get("org_type")
        phone = request.data.get("phone")
        email = request.data.get("email")
        request_status = request.data.get("status")
        notes = request.data.get("notes")

        create_org = False

        try:
            onboarding_request = OnboardOrganisationAccount.objects.get(id=id)
        except OnboardOrganisationAccount.DoesNotExist:
            return Response(
                {"message": "Onboarding request not found"}, status=status.HTTP_404_NOT_FOUND
            )
        
        if onboarding_request.status == "APPROVED":
            return Response(
                {"message": "Cannot modify details as this onboarding request is already approved"}, status=status.HTTP_403_FORBIDDEN
            )
        
        if onboarding_request.status == "REJECTED":
            return Response(
                {"message": "Cannot modify details as this onboarding request has been rejected previously"}, status=status.HTTP_403_FORBIDDEN
            )

        serialized_data = OnboardingOrgAccountSerializer(data=request.data,partial=True)
        try:
            serialized_data.is_valid(raise_exception=True)
        except Exception as e:
            error_data = ", ".join(list(e.args[0]))
            return Response(
                {"message": f"Invalid values provided for {error_data}"}, status=status.HTTP_400_BAD_REQUEST
            )

        if orgname is not None:
            onboarding_request.orgname = orgname

        if org_portal is not None:
            onboarding_request.org_portal = org_portal

        if email_domain_name is not None:
            onboarding_request.email_domain_name = email_domain_name

        if org_type is not None:
            onboarding_request.org_type = org_type

        if phone is not None:
            onboarding_request.phone = phone

        if email is not None:
            onboarding_request.email = email

        if request_status == onboarding_request.status:
            return Response(
                {"message": "This request is already in same status as requested"}, status=status.HTTP_403_FORBIDDEN
            )

        if request_status != "APPROVED":
            if request_status is not None:
                onboarding_request.status = request_status

            if notes is not None:
                notes = request_status+'||'+notes
                if onboarding_request.notes is None:
                    onboarding_request.notes = [notes]
                else:
                    onboarding_request.notes.append(notes)

        if onboarding_request.status != request_status and request_status == "APPROVED":
            create_org = True
        
        onboarding_request.save()

        if create_org == True:
            org_create_obj = OrganizationViewSet()
            request.data["title"] = onboarding_request.orgname
            request.data["email_domain_name"] = onboarding_request.email_domain_name
            request.data["new_org_owner_email"] = onboarding_request.email
            # Onboard with default values
            request.data["default_transcript_type"] = "MACHINE_GENERATED"
            request.data["default_translation_type"] = "MACHINE_GENERATED"
            request.data["default_voiceover_type"] = "MACHINE_GENERATED"
            resp=org_create_obj.create(request)
            if resp.status_code == 200:
                if request_status is not None:
                    onboarding_request.status = request_status

                if notes is not None:
                    notes = request_status+'||'+notes
                    if onboarding_request.notes is None:
                        onboarding_request.notes = [notes]
                    else:
                        onboarding_request.notes.append(notes)
                onboarding_request.save()
            return resp

        return Response(
            {"message": "Onboarding request data updated successfully."}, status=status.HTTP_200_OK
        )