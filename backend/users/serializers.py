from rest_framework import serializers
from organization.serializers import OrganizationSerializer
from .models import User
from django.contrib.auth import password_validation
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers
from newsletter.serializers import SubscribedUsersSerializers
from newsletter.models import SubscribedUsers
from djoser.serializers import TokenCreateSerializer
from django.contrib.auth import authenticate
from rest_framework.exceptions import ValidationError
from django.contrib.auth.hashers import check_password
from rest_framework_simplejwt.tokens import RefreshToken
class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(max_length=128, write_only=True, required=True)
    new_password1 = serializers.CharField(
        max_length=128, write_only=True, required=True
    )

    def match_old_password(self, instance, value):
        if not instance.check_password(value["old_password"]):
            return False
        return True

    def validate(self, instance, data):
        if data["new_password1"] != data["new_password2"]:
            return False
        password_validation.validate_password(data["new_password1"], instance)
        return True

    def save(self, instance, validated_data):
        instance.set_password(validated_data.get("new_password1"))
        instance.save()
        return instance


class UserSignUpSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            "username",
            "password",
            "email",
            "first_name",
            "last_name",
            "phone",
            "languages",
        ]

    def update(self, instance, validated_data):
        instance.username = validated_data.get("username")
        instance.has_accepted_invite = True
        instance.set_password(validated_data.get("password"))
        instance.save()
        return instance


class UpdateUserPasswordSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            "password",
        ]

    def update(self, instance, validated_data):
        instance.set_password(validated_data.get("password"))
        instance.save()
        return instance


class UserUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            "username",
            "email",
            "first_name",
            "last_name",
            "availability_status",
            "phone",
            "enable_mail",
            "languages",
        ]
        read_only_fields = ["email"]


class UserUpdateSerializerOrgOwner(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            "username",
            "email",
            "first_name",
            "last_name",
            "availability_status",
            "phone",
            "enable_mail",
            "role",
            "organization",
            "languages",
        ]
        read_only_fields = ["email"]


class CustomTokenCreateSerializer(TokenCreateSerializer):
    def validate(self, attrs):
        email = attrs.get('email')
        password = attrs.get('password')

        if not email:
            raise ValidationError({"detail": _("Email field is required.")})

        # Authenticate using the custom email-based backend
        user = authenticate(email=email, password=password)

        if user is None:
            # Check if the email exists in the database
            if User.objects.filter(email=email).exists():
                raise ValidationError({"detail": _("Email and password do not match.")})
            else:
                raise ValidationError({"detail": _("User does not exist.")})

        # Return tokens after successful authentication
        refresh = RefreshToken.for_user(user)
        
        return {
            'refresh': str(refresh),
            'access': str(refresh.access_token),
            
        }
    










# class CustomTokenCreateSerializer(TokenCreateSerializer):
#     def validate(self, attrs):
#         email = attrs.get('email')
#         password = attrs.get('password')

#         if not email:
#             raise ValidationError({"detail": _("Email field is required.")})

#         # Authenticate using the custom email-based backend
#         user = authenticate(email=email, password=password)

#         if user is None:
#             # Check if the email exists in the database
#             if User.objects.filter(email=email).exists():
#                 raise ValidationError({"detail": _("Email and password do not match.")})
#             else:
#                 raise ValidationError({"detail": _("User does not exist.")})

#         # Return tokens after successful authentication
#         return super().validate(attrs)
   


class UserProfileSerializer(serializers.ModelSerializer):
    organization = OrganizationSerializer(read_only=True)
    role_label = serializers.CharField(source="get_role_label")
    subscribed_info = serializers.SerializerMethodField()

    def get_subscribed_info(self, obj):
        subscribed_obj = SubscribedUsers.objects.filter(user=obj).first()
        if subscribed_obj is not None:
            return {
                "categories": subscribed_obj.subscribed_categories,
                "email": subscribed_obj.email,
            }
        else:
            subscribed_obj = SubscribedUsers.objects.create(
                user=obj,
                email=obj.email,
                subscribed_categories=["Release", "Downtime", "General"],
            )
            return {
                "categories": subscribed_obj.subscribed_categories,
                "email": subscribed_obj.email,
            }

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "email",
            "has_accepted_invite",
            "availability_status",
            "enable_mail",
            "first_name",
            "last_name",
            "phone",
            "role",
            "role_label",
            "organization",
            "unverified_email",
            "date_joined",
            "languages",
            "subscribed_info",
            "tips",
            "user_history",
        ]
        read_only_fields = [
            "id",
            "email",
            "role",
            "role_label",
            "organization",
            "unverified_email",
            "date_joined",
        ]


class UserFetchSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "role",
            "has_accepted_invite",
            "languages",
        ]
        read_only_fields = [
            "id",
            "email",
            "role",
            "has_accepted_invite",
        ]


class LanguageSerializer(serializers.Serializer):
    language = serializers.ListField(child=serializers.CharField())


class UserEmailSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["email"]
