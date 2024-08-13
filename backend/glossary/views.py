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
from users.models import User
from transcript.metadata import TRANSCRIPTION_LANGUAGE_CHOICES
from translation.metadata import TRANSLATION_LANGUAGE_CHOICES
from .models import DOMAIN_CHOICES
from rest_framework.decorators import api_view
import logging
from organization.models import Organization
import base64
import io
import csv
from django.http import HttpRequest


accepted_domain_choices = [domain[1] for domain in DOMAIN_CHOICES]
transcription_accepted_languages = [
    language[0] for language in TRANSCRIPTION_LANGUAGE_CHOICES
]
translation_accepted_languages = [
    language[0] for language in TRANSLATION_LANGUAGE_CHOICES
]
required_fields_glossary = [
    "Source Language",
    "Target Language",
    "Source Text",
    "Target Text",
    "Contributor",
    "Domain",
]


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
        user_id = str(request.data.get("user_id", "")) or str(request.user.id)
        user_obj = User.objects.get(pk=user_id)
        for sentence in request.data.get("sentences"):
            glossary_obj = Glossary.objects.filter(
                source_text=sentence["src"],
                target_text=sentence["tgt"],
                user_id=user_obj.id,
                source_language=sentence["locale"].split("|")[0],
                target_language=sentence["locale"].split("|")[1],
            ).first()
            if glossary_obj is not None:
                return Response(
                    {"message": "Glossary already exists."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            tmx_input = {
                "userID": user_id,
                "sentences": [
                    {
                        "src": sentence["src"],
                        "tgt": sentence["tgt"],
                        "locale": sentence["locale"],
                        "context": sentence["domain"],
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

    @swagger_auto_schema(
        method="DELETE",
        manual_parameters=[
            openapi.Parameter(
                "sentences",
                openapi.IN_QUERY,
                description=("Glossary to delete."),
                type=openapi.TYPE_OBJECT,
                required=True,
            ),
        ],
        responses={409: "There are conflicts with this task."},
    )
    @action(detail=False, methods=["delete"], url_path="delete_glossary")
    def delete_glossary(self, request, *args, **kwargs):
        """
        Delete a project
        """
        sentence_param = json.loads(request.query_params.get("sentences"))
        service = TMXService()
        data = {
            "userID": str(request.user.id),
            "sentences": [
                {
                    "src": sentence_param[0]["src"],
                    "locale": sentence_param[0]["locale"],
                    "tgt": sentence_param[0]["tgt"],
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
    @action(detail=False, methods=["get"], url_path="populate")
    def populate(self, request):
        tmx_service = TMXService()
        glossary_entries = Glossary.objects.all()
        for entry in glossary_entries:
            tmx_input = {
                "sentences": [
                    {
                        "src": entry.source_text,
                        "tgt": entry.target_text,
                        "locale": f"{entry.source_language}|{entry.target_language}",
                        "context": entry.context,
                    }
                ],
                "userID": f"{entry.user_id.id}",
                "orgID": None,
            }
            tmx_service.push_to_tmx_store(tmx_input)
        return Response(
            {"message": "Glossary updated"},
            status=status.HTTP_200_OK,
        )
    
    @swagger_auto_schema(
        method="post",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=["csv", "org_id"],
            properties={
                "org_id": openapi.Schema(
                    type=openapi.TYPE_INTEGER,
                    description="An integer identifying the organization instance",
                ),
                "csv": openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description="A string to pass the csv data",
                ),
            },
        ),
        responses={
            200: "CSV uploaded successfully",
        },
    )
    
    @action(detail=False, methods=["post"], url_path="upload_glossary")
    def upload_glossary(self, request, *args, **kwargs):
        logging.info("Calling Upload API for Glossary...")
        org_id = request.data.get("org_id")
        csv_content = request.data.get("csv")

        try:
            org = Organization.objects.get(pk=org_id)
        except Organization.DoesNotExist:
            return Response(
                {"message": "Organization not found"}, status=status.HTTP_404_NOT_FOUND
            )

        if org.organization_owner.id != request.user.id:
            return Response(
                {"message": "You are not allowed to upload CSV."},
                status=status.HTTP_403_FORBIDDEN,
            )
        decrypted = base64.b64decode(csv_content).decode("utf-8")
        csv_data = []
        with io.StringIO(decrypted) as fp:
            reader = csv.reader(fp, delimiter=",", quotechar='"')
            for row in reader:
                new_row = ",".join(row)
                csv_data.append(new_row)

        if len(csv_data) > 200:
            return Response(
                {"message": "Number of rows is greater than 200."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        csv_reader = csv.DictReader(csv_data)
        if not set(required_fields_glossary).issubset(csv_reader.fieldnames):
            return Response(
                {
                    "message": f"Missing columns: {', '.join(set(required_fields_glossary) - set(csv_reader.fieldnames))}"
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if csv_reader.fieldnames != required_fields_glossary:
            return Response(
                {"message": "The sequence of fields given in CSV is wrong."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        errors = []
        row_num = 0

        valid_rows = []

        for row in csv_reader:
            valid_row = {}
            row_num += 1
            source_language = row["Source Language"]
            target_language = row["Target Language"]
            source_text = row["Source Text"]
            target_text = row["Target Text"]
            user_email = row["Contributor"]

            user_obj = User.objects.get(email=user_email)
            if user_obj is None:
                errors.append(
                    {
                        "row_no": f"Row {row_num}",
                        "message": f"User does not belong to this organization: {row['Contributor']}",
                    }
                )
                continue
            valid_row["user_id"] = user_obj.id
            if (
                not isinstance(row["Source Language"], str)
                or row["Source Language"] not in transcription_accepted_languages
            ):
                errors.append(
                    {
                        "row_no": f"Row {row_num}",
                        "message": f"Invalid source language: {row['Source Language']}",
                    }
                )
            else:
                valid_row["source_language"] = row["Source Language"]

            if (
                not isinstance(row["Target Language"], str)
                or row["Target Language"] not in translation_accepted_languages
            ):
                errors.append(
                    {
                        "row_no": f"Row {row_num}",
                        "message": f"Invalid target language: {row['Target Language']}",
                    }
                )
            else:
                valid_row["target_language"] = row["Target Language"]

            if not isinstance(row["Source Text"], str):
                errors.append(
                    {
                        "row_no": f"Row {row_num}",
                        "message": f"Invalid source text: {row['Source Text']}",
                    }
                )
            else:
                valid_row["source_text"] = row["Source Text"]

            if not isinstance(row["Target Text"], str):
                errors.append(
                    {
                        "row_no": f"Row {row_num}",
                        "message": f"Invalid target text: {row['Target Text']}",
                    }
                )
            else:
                valid_row["target_text"] = row["Target Text"]

            if (
                not isinstance(row["Domain"], str)
                or row["Domain"] not in accepted_domain_choices
            ):
                errors.append(
                    {
                        "row_no": f"Row {row_num}",
                        "message": f"Invalid Domain: {row['Domain']}",
                    }
                )
            else:
                valid_row["domain"] = row["Domain"]

            if len(errors) == 0:
                valid_rows.append(valid_row)

        if len(errors) > 0:
            return Response(
                {"message": "Invalid CSV", "response": errors},
                status=status.HTTP_400_BAD_REQUEST,
            )
        else:
            for row in valid_rows:
                new_request = HttpRequest()
                tmx_data = {
                    "user_id": row["user_id"],
                    "sentences": [
                        {
                            "src": row["source_text"],
                            "tgt": row["target_text"],
                            "locale": row["source_language"]
                            + "|"
                            + row["target_language"],
                            "domain": row["domain"],
                        }
                    ],
                }
                new_request.data = tmx_data
                # Call the post method to create a project
                glossary_creation = self.create(new_request)
            return Response(
                {"message": "CSV uploaded successfully"}, status=status.HTTP_200_OK
            )
