from users.models import User
from rest_framework.response import Response
from project.models import Project
from .models import Task
from functools import wraps
from rest_framework import status


PERMISSION_ERROR = {
    "message": "You do not have enough permissions to access this view!"
}
NO_PROJECT_FOUND = {"message": "No matching project found."}
NO_PROJECT_MANAGER_ERROR = {"message": "You are not a manager of this project!"}


def is_project_owner(f):
    @wraps(f)
    def wrapper(self, request, *args, **kwargs):
        if request.user.is_authenticated and (
            request.user.role == User.PROJECT_MANAGER
            or request.user.role == User.ORG_OWNER
            or request.user.role == User.ADMIN
            or request.user.is_superuser
        ):
            return f(self, request, *args, **kwargs)
        return Response(PERMISSION_ERROR, status=status.HTTP_403_FORBIDDEN)

    return wrapper


def has_task_edit_permission(f):
    @wraps(f)
    def wrapper(self, request, pk=None, *args, **kwargs):
        task = Task.objects.filter(pk=pk).first()
        if task is not None:
            project = Project.objects.filter(pk=task.video.project_id.id).first()
            if project is None:
                return Response(NO_PROJECT_FOUND, status=404)
            elif (
                request.user not in project.managers.all()
                and not request.user.is_superuser
                and request.user.role != User.ADMIN
                and request.user.role != User.ORG_OWNER
            ):
                return Response(NO_PROJECT_MANAGER_ERROR, status=403)
            else:
                print("Permission granted")
        else:
            return Response({"message": "Task not found."}, status=404)
        return f(self, request, pk, *args, **kwargs)

    return wrapper


def has_task_edit_permission_individual(f):
    @wraps(f)
    def wrapper(request, pk=None, *args, **kwargs):
        task = Task.objects.filter(pk=pk).first()
        if task is not None:
            project = Project.objects.filter(pk=task.video.project_id.id).first()
            if project is None:
                return Response(NO_PROJECT_FOUND, status=404)
            elif (
                request.user not in project.managers.all()
                and not request.user.is_superuser
                and request.user.role != User.ADMIN
                and request.user.role != User.ORG_OWNER
            ):
                return Response(NO_PROJECT_MANAGER_ERROR, status=403)
            else:
                print("Permission granted")
        else:
            return Response({"message": "Task not found."}, status=404)
        return f(request, pk, *args, **kwargs)

    return wrapper


def has_task_create_permission(video, user):
    project = Project.objects.filter(pk=video.project_id.id).first()
    if project is None:
        return Response(NO_PROJECT_FOUND, status=404)
    elif (
        user not in project.managers.all()
        and not user.is_superuser
        and user.role != User.ADMIN
        and user.role != User.ORG_OWNER
    ):
        return Response(NO_PROJECT_MANAGER_ERROR, status=403)
    else:
        return True
