from users.models import User
from rest_framework.response import Response
from .models import Organization
from functools import wraps
from rest_framework import status


PERMISSION_ERROR = {
    "message": "You do not have enough permissions to access this view!"
}

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
