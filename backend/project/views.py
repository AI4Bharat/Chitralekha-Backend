from rest_framework import viewsets
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import action
from rest_framework import status
from organization.decorators import is_organization_owner
from video.models import Video
from video.serializers import VideoSerializer
from users.models import User
from .models import Project
from .serializers import ProjectSerializer
from .decorators import is_project_owner
from users.serializers import UserFetchSerializer

class ProjectViewSet(viewsets.ModelViewSet):
    """
    Viewset for Project CRUD
    """

    queryset = Project.objects.all()
    serializer_class = ProjectSerializer
    permission_classes = (IsAuthenticated,)

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

    # add an endpoint to remove project members
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

    # Add endpoint for assigning project manager
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
                if user.role == 6:
                    if project.manager:
                        return Response(
                            {"error": "manager already assigned"},
                            status=status.HTTP_400_BAD_REQUEST,
                        )
                        return Response(
                            {"error": "manager already added"},
                            status=status.HTTP_400_BAD_REQUEST,
                        )
                    else:
                        project.manager = user
                        project.save()
                else:
                    return Response(
                        {"error": "user is not manager"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
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

    # add an endpoint to unassign project manager
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
                if user.role == 6:
                    if project.manager:
                        project.manager = None
                        project.save()
                    else:
                        return Response(
                            {"error": "manager not assigned"},
                            status=status.HTTP_400_BAD_REQUEST,
                        )
                else:
                    return Response(
                        {"error": "user is not manager"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
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

    # Add endpoint to list all related videos of a project (project_id)
    @action(
        detail=True,
        methods=["GET"],
        name="List Project Videos",
        url_name="list_project_videos",
    )
    @is_project_owner
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

        # Add endpoint to return all related videos using project_id

    @is_project_owner
    def update(self, request, pk=None, *args, **kwargs):
        """
        Update project details
        """
        return super().update(request, *args, **kwargs)

    @is_project_owner
    def partial_update(self, request, pk=None, *args, **kwargs):
        return super().partial_update(request, *args, **kwargs)

    @is_project_owner
    def destroy(self, request, pk=None, *args, **kwargs):
        """
        Delete a project
        """
        return super().delete(request, *args, **kwargs)

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
        return Response(serializer.data)
