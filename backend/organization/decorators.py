from users.models import User
from rest_framework.response import Response
from .models import Organization
from functools import wraps

PERMISSION_ERROR = {
    "message": "You do not have enough permissions to access this view!"
}
NO_ORGANIZATION_FOUND = {"message": "No matching organization found."}
NO_ORGANIZATION_OWNER_ERROR = {"message": "You do not belong to this organization!"}


# Allow view only if is a organization owner.
def is_organization_owner(f):
    @wraps(f)
    def wrapper(self, request, *args, **kwargs):
        if request.user.is_authenticated and (
            request.user.role == User.ORG_OWNER
            or User.ADMIN
            or request.user.is_superuser
        ):
            return f(self, request, *args, **kwargs)
        return Response(PERMISSION_ERROR, status=403)

    return wrapper


def is_admin(f):
    @wraps(f)
    def wrapper(self, request, *args, **kwargs):
        if request.user.is_authenticated and (
            request.user.role == User.ADMIN or request.user.is_superuser
        ):
            return f(self, request, *args, **kwargs)
        return Response(PERMISSION_ERROR, status=403)

    return wrapper


# Allow detail view only if user is a particular organization's owner.
def is_particular_organization_owner(f):
    @wraps(f)
    def wrapper(self, request, pk=None, *args, **kwargs):
        if (
            request.user.role == User.ORG_OWNER
            or User.ADMIN
            or request.user.is_superuser
        ):
            if "organization" in request.data:
                organization = Organization.objects.filter(
                    pk=request.data["organization"]
                ).first()
            else:
                organization = Organization.objects.filter(pk=pk).first()

            if not organization:
                return Response(NO_ORGANIZATION_FOUND, status=404)
            elif (
                not organization.organization_owners.filter(id=request.user.id).exists()
                and not request.user.is_superuser
                and request.user.role != User.ADMIN
            ):
                return Response(NO_ORGANIZATION_OWNER_ERROR, status=403)

            return f(self, request, pk, *args, **kwargs)
        else:
            return Response(PERMISSION_ERROR, status=403)

    return wrapper
