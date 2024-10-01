import os
from http.client import responses
import secrets
import string
import itertools
from wsgiref.util import request_uri
from rest_framework import viewsets, status
import re
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.decorators import permission_classes
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from rest_framework_simplejwt.views import TokenObtainPairView
from .serializers import CustomTokenCreateSerializer

from .serializers import (
    ChangePasswordSerializer,
    UserProfileSerializer,
    UserSignUpSerializer,
    UserUpdateSerializer,
    UserUpdateSerializerOrgOwner,
    LanguageSerializer,
    UpdateUserPasswordSerializer,
)
from djoser.views import TokenCreateView
from django.contrib.auth import authenticate
from rest_framework.views import APIView
from organization.models import Invite, Organization
from organization.serializers import InviteGenerationSerializer
from organization.decorators import is_admin, is_organization_owner
from project.decorators import is_project_owner
from users.models import LANG_CHOICES, User
from organization.models import OnboardOrganisationAccount
from rest_framework.decorators import action
from django.db.models import Q
from datetime import datetime
from django.conf import settings
from django.core.mail import send_mail, EmailMultiAlternatives
from rest_framework.generics import UpdateAPIView
from task.models import Task
from task.serializers import TaskSerializer
from project.models import Project
from project.serializers import ProjectSerializer
import json
import datetime
from config import point_of_contacts, app_name
import ast
from utils.email_template import send_email_template, invite_email_template

regex = r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"


def generate_random_string(length=12):
    return "".join(
        secrets.choice(string.ascii_uppercase + string.digits) for i in range(length)
    )


onboarding_table = """
        <!DOCTYPE html>
        <html lang="en">
        <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Organization Information</title>
        <style>
        table {{
          width: 100%;
          border-collapse: collapse;
          border-radius: 8px;
          overflow: hidden;
        }}

        th, td {{
          padding: 12px;
          text-align: left;
        }}

        th {{
          background-color: #4CAF50;
          color: white;
        }}

        tr:nth-child(even) {{
          background-color: #f2f2f2;
        }}

        tr:hover {{
          background-color: #ddd;
        }}

        td:first-child {{
          font-weight: bold;
        }}

        td {{
          border-bottom: 1px solid #ddd;
        }}

        </style>
        </head>
        <body>

        <h2 style="text-align: center; color: #4CAF50;">Organization Information</h2>

        <table>
          <tr>
            <th>Field</th>
            <th>Value</th>
          </tr>
          <tr>
            <td>Organization Name</td>
            <td>{org_name}</td>
          </tr>
          <tr>
            <td>Organization Portal</td>
            <td>{org_portal}</td>
          </tr>
          <tr>
            <td>Email ID</td>
            <td>{email_id}</td>
          </tr>
          <tr>
            <td>Phone</td>
            <td>{phone}</td>
          </tr>
          <tr>
            <td>Organization Type</td>
            <td>{org_type}</td>
          </tr>
          <tr>
            <td>Purpose</td>
            <td>{purpose}</td>
          </tr>
          <tr>
            <td>Source</td>
            <td>{source}</td>
          </tr>
          <tr>
            <td>Interested in using the tool for</td>
            <td>{interested_in}</td>
          </tr>
          <tr>
            <td>Source Language</td>
            <td>{src_language}</td>
          </tr>
          <tr>
            <td>Target Language</td>
            <td>{tgt_language}</td>
          </tr>
        </table>

        </body>
        </html>
"""

class CustomTokenCreateView(APIView):
    
    serializer_class = CustomTokenCreateSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data)
        
        if serializer.is_valid(raise_exception=True):
            token_data = serializer.validated_data  # This now contains the tokens
            return Response(token_data, status=status.HTTP_200_OK)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST) 


class OnboardingAPIView(APIView):
    def get(
        self,
        request,
        org_name,
        org_portal,
        email_id,
        phone,
        org_type,
        purpose,
        source,
        interested_in,
        src_language,
        tgt_language,
        *args,
        **kwargs,
    ):
        interested_in = ", ".join(str(interested_in).title().split(" "))
        onboarding_table_1 = onboarding_table.format(
            org_name=org_name,
            org_portal=org_portal,
            email_id=email_id,
            phone=phone,
            org_type=org_type,
            purpose=purpose,
            source=source,
            interested_in=interested_in,
            src_language=src_language.capitalize(),
            tgt_language=tgt_language.capitalize(),
        )
        # current_time = datetime.now()
        # formatted_date = current_time.strftime("%d %b")
        OnboardOrganisationAccount.objects.create(
            orgname=org_name,
            org_portal=org_portal,
            email=email_id,
            phone=phone,
            org_type=org_type,
            interested_in=interested_in,
            src_language=src_language,
            tgt_language=tgt_language,
            purpose=purpose,
            source=source,
        )

        contacts = ast.literal_eval(point_of_contacts)
        for email in contacts:
            subject = "OnBoarding Request for {}".format(org_name)
            message = f"<p> Hello! Please check the attachment for following onboarind requests information </p>"

            compiled_code = send_email_template(subject, message)
            msg = EmailMultiAlternatives(
                subject,
                compiled_code,
                settings.DEFAULT_FROM_EMAIL,
                [email],
            )
            with open("onboarding_request.html", "w") as email_file:
                email_file.write(onboarding_table_1)

            msg.attach_file("onboarding_request.html")
            msg.attach_alternative(compiled_code, "text/html")
            # send_mail(
            #     "OnBoarding Request for {}".format(org_name),
            #     "",
            #     settings.DEFAULT_FROM_EMAIL,
            #     [email],
            #     html_message=onboarding_table_1,
            # )
        return Response(
            {"message": "Onboarding request is submitted."},
            status=status.HTTP_404_NOT_FOUND,
        )


class InviteViewSet(viewsets.ViewSet):
    @swagger_auto_schema(request_body=InviteGenerationSerializer)
    @permission_classes((IsAuthenticated,))
    @action(
        detail=False, methods=["post"], url_path="generate", url_name="invite_users"
    )
    def invite_users(self, request):
        """
        Invite users to join your organization. This generates a new invite
        with an invite code or adds users to an existing one.
        """
        emails = request.data.get("emails")
        organization_id = request.data.get("organization_id")
        users = []

        if organization_id is not None:
            try:
                org = Organization.objects.get(id=organization_id)
                org_id = org.id
            except Organization.DoesNotExist:
                return Response(
                    {"message": "Organization not found"},
                    status=status.HTTP_200_OK,
                )
        else:
            org_id = None
            org = None
        valid_user_emails = []
        invalid_emails = []

        for email in emails:
            # Checking if the email is in valid format.
            if re.fullmatch(regex, email):
                try:
                    user = User(
                        username=generate_random_string(12),
                        email=email,
                        organization_id=org_id,
                        role=request.data.get("role"),
                    )
                    user.set_password(generate_random_string(10))
                    valid_user_emails.append(email)
                    users.append(user)
                except:
                    Response(
                        {"message": "User can't be added"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
            else:
                invalid_emails.append(email)
        if len(valid_user_emails) <= 0:
            return Response(
                {"message": "No valid emails found"}, status=status.HTTP_400_BAD_REQUEST
            )
        if len(invalid_emails) == 0:
            ret_dict = {"message": "Invites sent"}
            ret_status = status.HTTP_201_CREATED
        else:
            ret_dict = {
                "message": f"Invites sent partially! Invalid emails: {','.join(invalid_emails)}"
            }
            ret_status = status.HTTP_201_CREATED

        users = User.objects.bulk_create(users)

        Invite.create_invite(organization=org, users=users)
        return Response(ret_dict, status=status.HTTP_200_OK)

    @is_admin
    @swagger_auto_schema(
        method="post",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=["org_name", "email", "roles"],
            properties={
                "org_name": openapi.Schema(
                    type=openapi.TYPE_STRING, description="Name of the organization"
                ),
                "email": openapi.Schema(
                    type=openapi.TYPE_STRING,
                    format=openapi.FORMAT_EMAIL,
                    description="Email of the organization",
                ),
                "roles": openapi.Schema(
                    type=openapi.TYPE_ARRAY,
                    items=openapi.Items(type=openapi.TYPE_STRING),
                    description="List of roles",
                ),
            },
        ),
        responses={200: "Organization and users created successfully"},
    )
    @action(
        detail=False,
        methods=["post"],
        url_path="create_onboarding_account",
        url_name="create_onboarding_account",
    )
    def create_onboarding_account(self, request):
        org_name = request.data.get("org_name")
        org_email = request.data.get("email")
        roles = request.data.get("roles")
        try:
            organization = Organization.objects.get(title=org_name)
        except:
            return Response(
                {"message": "Organization not found."}, status=status.HTTP_404_NOT_FOUND
            )
        first_word = org_name.split()[0]
        password = f"demo@{first_word}"
        created_emails = []
        existing_emails = []
        if roles:
            for r in roles:
                email = f"{r.lower()}@{first_word.lower()}.org"
                role_firstword = f"{r.lower()}_{first_word}"
                f_name = email.split("@")[0].replace("_", " ")
                try:
                    role_user = User.objects.create_user(
                        username=role_firstword,
                        email=email,
                        password=password,
                        has_accepted_invite=True,
                        role=r,
                        first_name=f_name,
                        organization=organization,
                        languages=["English", "Hindi"],
                    )
                    created_emails.append(email)
                except:
                    existing_emails.append(email)

        email_subject = f"Welcome to {app_name}"
        email_message = f'Hi,\n\nUsers have been registered to {app_name} under your organization {org_name}.\n\nCreated emails: {", ".join(created_emails)}\n\nPassword for all users: {password}\n\nPlease distribute these credentials to the users accordingly.\n\nBest regards,\nThe {app_name} Team'
        # send_mail(email_subject, email_message, settings.DEFAULT_FROM_EMAIL, [org_email])

        try:
            compiled_code = invite_email_template(email_subject, email_message)
            msg = EmailMultiAlternatives(
                email_subject,
                compiled_code,
                settings.DEFAULT_FROM_EMAIL,
                [org_email],
            )
            msg.attach_alternative(compiled_code, "text/html")
            msg.send()

        except Exception as e:
            print(e)

        if existing_emails:
            if created_emails:
                msg = (
                    ", ".join(existing_emails)
                    + " already exists. Other Users created successfully."
                )
                return Response({"message": msg}, status=status.HTTP_200_OK)
            else:
                msg = ", ".join(existing_emails) + " already exists."
                return Response({"message": msg}, status=status.HTTP_400_BAD_REQUEST)
        elif created_emails:
            msg = "Users successfully created."
            return Response({"message": msg}, status=status.HTTP_200_OK)

    @permission_classes([AllowAny])
    @swagger_auto_schema(request_body=UserSignUpSerializer)
    @action(detail=True, methods=["patch"], url_path="accept", url_name="sign_up_user")
    def sign_up_user(self, request, pk=None):
        """
        Users to sign up for the first time.
        """
        email = request.data.get("email")
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response(
                {"message": "User not found"}, status=status.HTTP_404_NOT_FOUND
            )

        if user.has_accepted_invite:
            return Response(
                {"message": "User has already accepted invite"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            Invite.objects.get(user=user, invite_code=pk)
        except Invite.DoesNotExist:
            return Response(
                {"message": "Invite not found"}, status=status.HTTP_404_NOT_FOUND
            )

        serialized = UserSignUpSerializer(user, request.data)
        if serialized.is_valid():
            user.first_name = request.data.get("first_name", "")
            user.last_name = request.data.get("last_name", "")
            user.languages = request.data.get("languages")
            user.date_joined = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            serialized.save()
            return Response({"message": "User signed up"}, status=status.HTTP_200_OK)
        else:
            return Response(
                {"message": "Input values are incorrect."},
                status=status.HTTP_400_BAD_REQUEST,
            )

    @permission_classes([AllowAny])
    @action(
        detail=True,
        methods=["get"],
        url_path="get_invited_user_info",
        url_name="get_invited_user_info",
    )
    def get_invited_user_info(self, request, pk=None):
        """
        Users to sign up for the first time.
        """
        try:
            invite = Invite.objects.get(invite_code=pk)
        except Invite.DoesNotExist:
            return Response(
                {"message": "Invite not found"}, status=status.HTTP_404_NOT_FOUND
            )
        return Response(UserProfileSerializer(invite.user).data)

    @swagger_auto_schema(request_body=InviteGenerationSerializer)
    @permission_classes((IsAuthenticated,))
    @is_organization_owner
    @action(detail=False, methods=["post"], url_path="regenerate", url_name="re_invite")
    def re_invite(self, request):
        """
        The invited user are again invited if they have not accepted the
        invitation previously.
        """
        all_emails = request.data.get("emails")
        distinct_emails = list(set(all_emails))
        existing_emails_set = set(Invite.objects.values_list("user__email", flat=True))
        # absent_users- for those who have never been invited
        # present_users- for those who have been invited earlier
        (
            absent_user_emails,
            present_users,
            present_user_emails,
            already_accepted_invite,
        ) = ([], [], [], [])
        for user_email in distinct_emails:
            if user_email in existing_emails_set:
                user = User.objects.get(email=user_email)
                if user.has_accepted_invite:
                    already_accepted_invite.append(user_email)
                    continue
                present_users.append(user)
                present_user_emails.append(user_email)
            else:
                absent_user_emails.append(user_email)
        if present_users:
            Invite.re_invite(users=present_users)
        # setting up error messages
        (
            message_for_already_invited,
            message_for_absent_users,
            message_for_present_users,
        ) = ("", "", "")
        if already_accepted_invite:
            message_for_already_invited = (
                f" {','.join(already_accepted_invite)} have already accepted invite"
            )
        if absent_user_emails:
            message_for_absent_users = (
                f"Kindly send a new invite to: {','.join(absent_user_emails)}"
            )
        if present_user_emails:
            message_for_present_users = f"{','.join(present_user_emails)} re-invited"
        extra_data = {
            "user_email": request.user.email,
            "request_path": "/regenerate",
        }
        if absent_user_emails and present_user_emails:
            # logger.info("Re_invite sent successfully", extra=extra_data)
            return Response(
                {
                    "message": message_for_absent_users
                    + ", "
                    + message_for_present_users
                    + "."
                    + message_for_already_invited
                },
                status=status.HTTP_201_CREATED,
            )
        elif absent_user_emails:
            # logger.info("Re_invite was not sent", extra=extra_data)
            return Response(
                {
                    "message": message_for_absent_users
                    + "."
                    + message_for_already_invited
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        elif present_user_emails:
            # logger.info("Re_invite sent successfully", extra=extra_data)
            return Response(
                {
                    "message": message_for_present_users
                    + "."
                    + message_for_already_invited
                },
                status=status.HTTP_201_CREATED,
            )
        else:
            # logger.info("Re_invite sent successfully", extra=extra_data)
            return Response(
                {"message": message_for_already_invited}, status=status.HTTP_201_CREATED
            )


class UserViewSet(viewsets.ViewSet):
    permission_classes = (IsAuthenticated,)

    @swagger_auto_schema(request_body=UserUpdateSerializer)
    @action(detail=False, methods=["patch"], url_path="update", url_name="edit_profile")
    def edit_profile(self, request):
        """
        Updating user profile.
        """
        user = request.user
        serialized = UserUpdateSerializer(user, request.data, partial=True)

        if serialized.is_valid():
            serialized.save()
            return Response(
                {"message": "User profile edited"}, status=status.HTTP_200_OK
            )

    @swagger_auto_schema(request_body=ChangePasswordSerializer)
    @action(
        detail=True,
        methods=["patch"],
        url_path="update_my_password",
        url_name="update_my_password",
    )
    def update_password(self, request, pk=None, *args, **kwargs):
        try:
            user = User.objects.get(pk=pk)
        except User.DoesNotExist:
            return Response(
                {"message": "User not found"}, status=status.HTTP_404_NOT_FOUND
            )
        serializer = ChangePasswordSerializer(user, request.data)

        if not serializer.match_old_password(user, request.data):
            return Response(
                {
                    "message": "Your old password was entered incorrectly. Please enter it again."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = serializer.save(user, request.data)
        return Response(
            {"message": "User password changed."}, status=status.HTTP_200_OK
        )

    @is_admin
    @swagger_auto_schema(request_body=UpdateUserPasswordSerializer)
    @action(
        detail=True,
        methods=["patch"],
        url_path="update_password",
        url_name="set_password",
    )
    def user_set_password(self, request, pk=None):
        """
        Users to sign up for the first time.
        """
        try:
            user = User.objects.get(pk=pk)
        except User.DoesNotExist:
            return Response(
                {"message": "User not found"}, status=status.HTTP_404_NOT_FOUND
            )

        serialized = UpdateUserPasswordSerializer(user, request.data)
        if serialized.is_valid():
            serialized.save()
            return Response(
                {"message": "User password changed."}, status=status.HTTP_200_OK
            )
        else:
            return Response(
                {"message": "Input values are incorrect."},
                status=status.HTTP_400_BAD_REQUEST,
            )

    @is_organization_owner
    @swagger_auto_schema(request_body=UserUpdateSerializerOrgOwner)
    @action(
        detail=True, methods=["patch"], url_path="update", url_name="edit_user_profile"
    )
    def edit_user_profile(self, request, pk=None):
        """
        Updating user profile.
        """
        user_obj = User.objects.get(pk=pk)
        user = request.user
        serialized = UserUpdateSerializerOrgOwner(user_obj, request.data, partial=True)

        if serialized.is_valid():
            serialized.save()
            return Response(
                {"message": "User profile edited"}, status=status.HTTP_200_OK
            )

    @swagger_auto_schema(responses={200: UserProfileSerializer})
    @action(detail=False, methods=["get"], url_path="me/fetch")
    def fetch_profile(self, request):
        """
        Fetches profile for logged in user
        """
        serialized = UserProfileSerializer(request.user)
        return Response(serialized.data, status=status.HTTP_200_OK)

    @swagger_auto_schema(
        method="patch",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                "tips": openapi.Schema(
                    type=openapi.TYPE_BOOLEAN, format="tips", description="tips"
                )
            },
            required=["tips"],
        ),
    )
    @action(detail=False, methods=["patch"], url_path="tips", url_name="update_tips")
    def update_tips(self, request, pk=None):
        """
        Checks if first-time-user and updates tip settings
        """
        user = request.user
        tip_setting = request.data.get("tips", None)

        if tip_setting is None:
            return Response(
                {"error": "Tips setting is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not isinstance(tip_setting, bool):
            return Response(
                {"error": "Tips setting must be a boolean value"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user.tips = tip_setting
        user.save()

        return Response(
            {"message": "Tips updated successfully"}, status=status.HTTP_200_OK
        )

    @swagger_auto_schema(responses={200: UserProfileSerializer})
    @action(detail=True, methods=["get"], url_path="fetch")
    def fetch_other_profile(self, request, pk=None):
        """
        Fetches profile for any user
        """
        try:
            user = User.objects.get(id=pk)
        except User.DoesNotExist:
            return Response(
                {"message": "User not found"}, status=status.HTTP_404_NOT_FOUND
            )
        serialized = UserProfileSerializer(user)
        return Response(serialized.data, status=status.HTTP_200_OK)

    @swagger_auto_schema(
        method="post",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                "email": openapi.Schema(
                    type=openapi.TYPE_STRING, format="email", description="New email"
                )
            },
            required=["email"],
        ),
        responses={
            200: "Verification email sent to both of your email ids.Please verify to update your email",
            403: "Please enter a valid email!",
        },
    )
    @action(
        detail=False, methods=["post"], url_path="update_email", url_name="update_email"
    )
    def update_email(self, request):
        """
        Updates the User Email
        """
        try:
            user = request.user
            unverified_email = request.data.get("email")

            old_email_update_code = generate_random_string(10)
            new_email_verification_code = generate_random_string(10)

            send_mail(
                "Email Verification",
                f"Your email verification code is:{old_email_update_code}",
                settings.DEFAULT_FROM_EMAIL,
                [user.email],
            )

            send_mail(
                "Email Verification",
                f"Your email verification code is:{new_email_verification_code}",
                settings.DEFAULT_FROM_EMAIL,
                [unverified_email],
            )

            user.unverified_email = unverified_email
            user.old_email_update_code = old_email_update_code
            user.new_email_verification_code = new_email_verification_code
            user.save()

            return Response(
                {
                    "message": "Verification email sent to both of your email ids.Please verify to update your email"
                },
                status=status.HTTP_200_OK,
            )
        except:
            return Response(
                {"message": "Please enter a valid email!"},
                status=status.HTTP_403_FORBIDDEN,
            )

    @swagger_auto_schema(
        method="post",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                "old_email_update_code": openapi.Schema(type=openapi.TYPE_STRING),
                "new_email_verification_code": openapi.Schema(type=openapi.TYPE_STRING),
            },
            required=["old_email_update_code", "new_email_verification_code"],
        ),
        responses={
            200: "Email verification Successful!",
            403: "Invalid verification codes!",
        },
    )
    @action(
        detail=False,
        methods=["post"],
        url_path="verify_email_updation",
        url_name="verify_email_updation",
    )
    def verify_email_updation(self, request):
        """
        Verify email updation
        """
        user = request.user
        if (user.unverified_email) != "":
            old_email_update_code = request.data.get("old_email_update_code")
            new_email_verification_code = request.data.get(
                "new_email_verification_code"
            )
            if (user.old_email_update_code) == old_email_update_code and (
                user.new_email_verification_code
            ) == new_email_verification_code:
                user.email = user.unverified_email
                user.unverified_email = ""
                user.old_email_update_code = ""
                user.new_email_verification_code = ""
                user.save()
                ret_dict = {"message": "Email verification Successful!"}
                ret_status = status.HTTP_200_OK
            else:
                ret_dict = {"message": "Invalid verification codes!"}
                ret_status = status.HTTP_403_FORBIDDEN
        else:
            ret_dict = {"message": "Invalid verification codes!"}
            ret_status = status.HTTP_403_FORBIDDEN

        return Response(ret_dict, status=ret_status)

    @swagger_auto_schema(
        method="post",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                "user_id": openapi.Schema(
                    type=openapi.TYPE_INTEGER, format="user_id", description="User Id"
                ),
                "enable_email": openapi.Schema(
                    type=openapi.TYPE_BOOLEAN,
                    format="email",
                    description="Enable Email",
                ),
            },
            required=["user_id"],
        ),
        responses={
            200: "Email enabled for the user",
            403: "Please enter a valid email!",
        },
    )
    @action(
        detail=False, methods=["post"], url_path="enable_email", url_name="enable_email"
    )
    def enable_email(self, request):
        """
        Update the mail enable service for any user
        """
        requested_id = request.data.get("user_id")
        enable_mail = request.data.get("enable_email")

        if enable_mail == True or enable_mail == False:
            pass
        else:
            return Response(
                {
                    "message": "please enter valid  input(True/False) for enable_mail field"
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            user = User.objects.get(id=requested_id)
        except User.DoesNotExist:
            return Response(
                {"message": "User not found"}, status=status.HTTP_404_NOT_FOUND
            )

        requested_id = request.data.get("user_id")

        if requested_id == request.user.id or (
            request.user.role == 3 and request.user.organization == user.organization
        ):
            user.enable_mail = enable_mail
            user.save()
            return Response(
                {"message": "Daily e-mail service settings changed."},
                status=status.HTTP_200_OK,
            )
        else:
            return Response(
                {"message": "Not Authorized"}, status=status.HTTP_403_FORBIDDEN
            )

    @swagger_auto_schema(
        method="get",
        manual_parameters=[
            openapi.Parameter(
                "role",
                openapi.IN_QUERY,
                description=("A string to get the role type e.g. ORG_OWNER"),
                type=openapi.TYPE_STRING,
                required=False,
            ),
            openapi.Parameter(
                "org_id",
                openapi.IN_QUERY,
                description=("A string to get the role type e.g. ORG_OWNER"),
                type=openapi.TYPE_INTEGER,
                required=False,
            ),
        ],
        responses={200: "Get all members who have signed up."},
    )
    @action(detail=False, methods=["GET"], name="Get all members", url_name="all_users")
    @is_admin
    def get_all_users(self, request):
        users = User.objects.filter(has_accepted_invite=True).all()
        serializer = UserProfileSerializer(users, many=True)
        if "role" in request.query_params:
            role = request.query_params["role"]
            if role == "ORG_OWNER":
                # Get all user IDs from organization owners
                owner_ids = Organization.objects.values_list(
                    "organization_owners", flat=True
                ).distinct()

                # Filter users based on these IDs
                organization_owners = users.filter(pk__in=owner_ids)

                # Filter users based on their roles
                user_by_roles = users.filter(role__in=["ORG_OWNER", "ADMIN"])
                if user_by_roles.count() == 0:
                    return Response(
                        {"message": "There is no user available with ORG_OWNER role."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                # Determine the set of users who are not organization owners
                users_set = set(user_by_roles) - set(organization_owners)

                # Check if 'org_id' is in the request query parameters
                if "org_id" in request.query_params:
                    org_id = request.query_params["org_id"]
                    try:
                        organization_obj = Organization.objects.get(pk=org_id)
                        # Get the organization owners and add them to the users_set
                        organization_owners_specific = (
                            organization_obj.organization_owners.all()
                        )
                        users_set.update(organization_owners_specific)
                    except Organization.DoesNotExist:
                        return Response(
                            {"message": "Organization not found."},
                            status=status.HTTP_404_NOT_FOUND,
                        )

                # Convert the set to a list if necessary for further processing
                users_list = list(users_set)
                serializer = UserProfileSerializer(list(users), many=True)
        return Response(serializer.data)


class RoleViewSet(viewsets.ViewSet):
    permission_classes = (AllowAny,)

    @action(detail=False, methods=["get"], url_path="get_roles")
    def get_roles(self, request):
        """
        Get all choices of role.
        """
        if not request.user.is_anonymous:
            user_role = request.user.role
            if user_role == "ORG_OWNER":
                data = [
                    {"label": role[1], "value": role[0]}
                    for role in User.ROLE_CHOICES[:8]
                ]
            elif user_role == "PROJECT_MANAGER":
                data = [
                    {"label": role[1], "value": role[0]}
                    for role in User.ROLE_CHOICES[:7]
                ]
            elif user_role == "ADMIN":
                data = [
                    {"label": role[1], "value": role[0]}
                    for role in User.ROLE_CHOICES[:9]
                ]
            else:
                data = [
                    {"label": role[1], "value": role[0]}
                    for role in User.ROLE_CHOICES[:9]
                ]
        else:
            data = [
                {"label": role[1], "value": role[0]} for role in User.ROLE_CHOICES[:9]
            ]

        return Response(data, status=status.HTTP_200_OK)

    @swagger_auto_schema(
        method="post",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                "user_id": openapi.Schema(type=openapi.TYPE_INTEGER),
                "role": openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description="role to be updated",
                ),
            },
            required=["user_id", "role"],
        ),
        responses={
            200: "User updated successfully",
            404: "User does not exist",
        },
    )
    @action(
        detail=False,
        methods=["POST"],
        name="Update user role",
        url_name="update_user_role",
    )
    @is_project_owner
    def update_user_role(self, request, *args, **kwargs):
        """
        API Endpoint to store parameter of youtube
        Endpoint: /users/update_user_role/
        Method: POST
        """

        user_id = request.data.get("user_id")
        role = request.data.get("role")

        try:
            user = User.objects.get(id=user_id)
            update_user_role = False
            check_if_tasks_assign = False

            if user.role == role:
                return Response(
                    {
                        "message": "Different role required",
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            elif (role == "ORG_OWNER") or (role == "ADMIN"):
                return Response(
                    {"message": f"Role can not be updated as {role}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            elif user.role == "PROJECT_MANAGER":
                projects = Project.objects.filter(managers__in=[user.id])
                if len(projects) > 0:
                    serializer_project = ProjectSerializer(projects, many=True)

                    return Response(
                        {
                            "message": "Reassign tasks to relevant users before role updated as PROJECT_MANAGER",
                            "data": serializer_project.data,
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )
            if role in itertools.chain(*User.ROLE_CHOICES):
                if user.role == "TRANSCRIPT_EDITOR":
                    if (
                        (role == "TRANSCRIPT_REVIEWER")
                        or (role == "UNIVERSAL_EDITOR")
                        or (role == "PROJECT_MANAGER")
                    ):
                        update_user_role = True
                    else:
                        check_if_tasks_assign = True
                elif user.role == "TRANSLATION_EDITOR":
                    if (
                        (role == "TRANSLATION_REVIEWER")
                        or (role == "UNIVERSAL_EDITOR")
                        or (role == "PROJECT_MANAGER")
                    ):
                        update_user_role = True
                    else:
                        check_if_tasks_assign = True
                elif user.role == "VOICEOVER_EDITOR":
                    if (
                        (role == "VOICEOVER_REVIEWER")
                        or (role == "UNIVERSAL_EDITOR")
                        or (role == "PROJECT_MANAGER")
                    ):
                        update_user_role = True
                    else:
                        check_if_tasks_assign = True
                elif user.role == "TRANSCRIPT_REVIEWER":
                    if (role == "UNIVERSAL_EDITOR") or (role == "PROJECT_MANAGER"):
                        update_user_role = True
                    else:
                        check_if_tasks_assign = True
                elif user.role == "TRANSLATION_REVIEWER":
                    if (role == "UNIVERSAL_EDITOR") or (role == "PROJECT_MANAGER"):
                        update_user_role = True
                    else:
                        check_if_tasks_assign = True
                elif user.role == "UNIVERSAL_EDITOR":
                    if role == "PROJECT_MANAGER":
                        update_user_role = True
                    else:
                        check_if_tasks_assign = True
                else:
                    return Response(
                        {"message": "Please enter a valid role"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                if check_if_tasks_assign:
                    tasks = Task.objects.filter(user=user).exclude(status="COMPLETE")
                    if len(tasks) > 0:
                        serializer = TaskSerializer(tasks, many=True)
                        serialized_dict = json.loads(json.dumps(serializer.data))
                        return Response(
                            {
                                "message": "Assign following tasks to the appropriate users and then proceed to update the role.",
                                "data": serialized_dict,
                            },
                            status=status.HTTP_400_BAD_REQUEST,
                        )
                    else:
                        update_user_role = True

                if update_user_role:
                    user.role = role
                    user.save()
                    response = {
                        "message": "Role is successfully updated.",
                    }
                    status_code = status.HTTP_200_OK
                else:
                    response = {
                        "message": "Unable to update role",
                    }
                    status_code = status.HTTP_400_BAD_REQUEST
            else:
                response = {
                    "message": "Role does not exist",
                }
                status_code = status.HTTP_404_NOT_FOUND

            return Response(
                response,
                status=status_code,
            )
        except User.DoesNotExist:
            return Response(
                {"message": "User does not exist"},
                status=status.HTTP_404_NOT_FOUND,
            )


class LanguageViewSet(viewsets.ViewSet):
    permission_classes = (AllowAny,)

    @swagger_auto_schema(responses={200: LanguageSerializer})
    @action(detail=False, methods=["get"], url_path="fetch")
    def fetch_language(self, request):
        """
        Fetches all language choices available to the user.
        """
        serialized = LanguageSerializer(
            data={"language": [lang[0] for lang in LANG_CHOICES]}
        )
        if serialized.is_valid():
            return Response(serialized.data, status=status.HTTP_200_OK)
        return Response(serialized.errors, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(
        detail=False,
        methods=["post"],
        url_path="modify_user_info",
        url_name="modify_user_info",
    )
    def temp_user_modify(self, request):
        users = User.objects.all()
        for user in users:
            if user.has_accepted_invite:
                if user.languages == None or len(user.languages) == 0:
                    user.languages = ["English", "Hindi"]
                    user.save()
                if user.phone == "":
                    user.phone = None
                    user.save()
        return Response([], status=status.HTTP_200_OK)
