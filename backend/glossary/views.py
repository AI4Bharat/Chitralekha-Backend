import os
from http.client import responses
from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.decorators import permission_classes
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from rest_framework.decorators import action
from glossary.serializers import GlossarySerializer
import json
import datetime
from .tmx.tmxservice import TMXService
from .models import Glossary


class GlossaryViewSet(ModelViewSet):
    """
    API ViewSet for the Glossary model.
    Performs CRUD operations on the Glossary model.
    Endpoint: /glossary/api
    Methods: GET, POST, PUT, DELETE
    """

    queryset = Glossary.objects.all()
    serializer_class = GlossarySerializer
    permission_classes = (IsAuthenticated,)

    def create(self, request, pk=None, *args, **kwargs):
        service = TMXService()
        # data = request.get_json()

        for sentence in request.data.get("sentences"):
            glossary_obj = Glossary.objects.filter(
                source_text=sentence["src"],
                target_text=sentence["tgt"],
                user_id=request.user,
            ).first()
            if glossary_obj is not None:
                return Response(
                    {"message": "Glossary already exists."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            tmx_input = {
                "userID": str(request.user.id),
                "sentences": [
                    {
                        "src": sentence["src"],
                        "tgt": sentence["tgt"],
                        "locale": sentence["locale"],
                    }
                ],
            }

        response = service.push_to_tmx_store(tmx_input)
        if type(response) == dict and response["status"] == "SUCCESS":
            return Response(
                {"message": "Glossary is successfully submitted."},
                status=status.HTTP_200_OK,
            )
        else:
            return Response(
                {"message": "Error in creating Glossary."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=False, methods=["get"], url_path="get_all")
    def get_all(self, request, pk=None, *args, **kwargs):
        service = TMXService()
        data = {"userID": str(request.user.id), "allUserKeys": False}
        try:
            tmx_data = service.get_tmx_data(data)
        except:
            return Response(
                {"message": "Error in returning Glossary."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        tmx_response = []
        count = 0
        for data in tmx_data:
            tmx_dict = {}
            count += 1
            tmx_dict["id"] = count
            tmx_dict["source_text"] = data["src"]
            tmx_dict["target_text"] = data["user_tgt"]
            tmx_dict["source_language"] = data["locale"].split("|")[0]
            tmx_dict["target_language"] = data["locale"].split("|")[1]
            tmx_response.append(tmx_dict)
        return Response(
            {"tmx_keys": tmx_response},
            status=status.HTTP_200_OK,
        )

    @swagger_auto_schema(request_body=GlossarySerializer)
    @action(detail=False, methods=["delete"], url_path="delete_key")
    def delete_key(self, request, *args, **kwargs):
        """
        Delete a project
        """
        service = TMXService()
        data = {
            "userID": str(request.user.id),
            "sentences": [
                {
                    "src": request.data.get("sentences")[0]["src"],
                    "locale": request.data.get("sentences")[0]["locale"],
                    "tgt": request.data.get("sentences")[0]["src"],
                }
            ],
        }
        response = service.delete_from_tmx_store(data)
        if response["status"] == "FAILED":
            return Response(
                {"message": "Error in deleting Glossary."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        else:
            return Response(
                {"message": "Glossary is successfully deleted."},
                status=status.HTTP_200_OK,
            )
