from users.models import User
from rest_framework.response import Response
from organization.models import Organization
from functools import wraps

PERMISSION_ERROR = {
    "message": "You do not have enough permissions to access this view!"
}

# Allow view only if user has translation editor or above roles.
def is_translation_editor(f):
    @wraps(f)
    def wrapper(request):
        if request.user.is_authenticated and (
            request.user.role == User.TRANSLATION_EDITOR
            or request.user.role == User.TRANSLATION_REVIEWER
            or request.user.role == User.UNIVERSAL_EDITOR
            or request.user.role == User.PROJECT_MANGAGER
            or request.user.role == User.ORG_OWNER
            or request.user.is_superuser
        ):
            return f(request)
        return Response(PERMISSION_ERROR, status=403)

    return wrapper
