from users.models import User
from rest_framework.response import Response
from functools import wraps
from rest_framework import status

PERMISSION_ERROR = {
    "message": "You do not have enough permissions to access this view!"
}


def is_transcript_editor(f):
    @wraps(f)
    def wrapper(request):
        if request.user.is_authenticated and (
            request.user.role == User.TRANSCRIPT_EDITOR
            or request.user.role == User.UNIVERSAL_EDITOR
            or request.user.role == User.TRANSCRIPT_REVIEWER
            or request.user.role == User.PROJECT_MANGAGER
            or request.user.role == User.ORG_OWNER
            or request.user.is_superuser
        ):
            return f(request)
        return Response(PERMISSION_ERROR, status=403)

    return wrapper
