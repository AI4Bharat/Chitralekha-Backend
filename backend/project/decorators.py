from users.models import User
from rest_framework.response import Response
from .models import Project
from task.models import Task
from functools import wraps
from rest_framework import status


PERMISSION_ERROR = {
    "message": "You do not have enough permissions to access this view!"
}
NO_PROJECT_FOUND = {"message": "No matching project found."}
NO_PROJECT_MANAGER_ERROR = {"message": "You are not a manager of this project!"}


# Allow view only if user has translation editor or above roles.
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


def is_particular_project_owner(f):
    @wraps(f)
    def wrapper(self, request, pk=None, *args, **kwargs):
        if (
            request.user.role == User.PROJECT_MANAGER
            or request.user.role == User.ORG_OWNER
            or request.user.role == User.ADMIN
            or request.user.is_superuser
        ):
            project = Project.objects.filter(pk=pk).first()
            if project is None:
                return Response(NO_PROJECT_FOUND, status=404)
            elif (
                request.user not in project.managers.all()
                and not request.user.is_superuser
                and request.user.role != User.ADMIN
                and request.user.role != User.ORG_OWNER
            ):
                return Response(NO_PROJECT_MANAGER_ERROR, status=403)
            return f(self, request, pk, *args, **kwargs)
        else:
            return Response(PERMISSION_ERROR, status=403)

    return wrapper
