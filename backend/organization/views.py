from rest_framework import viewsets
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import action
from rest_framework import status

from .models import Organization
from .serializers import OrganizationSerializer
from .decorators import is_organization_owner


class OrganizationViewSet(viewsets.ModelViewSet):
    """
    Viewset for Organization CRUD
    """

    queryset = Organization.objects.all()
    serializer_class = OrganizationSerializer
    permission_classes = (IsAuthenticated,)

    @is_organization_owner
    def create(self, request, pk=None, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @is_organization_owner
    def update(self, request, pk=None, *args, **kwargs):
        return super().update(request, *args, **kwargs)

    @is_organization_owner
    def partial_update(self, request, pk=None, *args, **kwargs):
        return super().partial_update(request, *args, **kwargs)

    @is_organization_owner
    def destroy(self, request, *args, **kwargs):
        return Response(
            {"message": "Deleting of Organizations is not supported!"},
            status=status.HTTP_403_FORBIDDEN,
        )
