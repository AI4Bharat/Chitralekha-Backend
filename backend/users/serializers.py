from rest_framework import serializers
from organization.serializers import OrganizationSerializer
from .models import User


class UserSignUpSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            "username",
            "password",
            "email",
            "first_name",
            "last_name",
            "languages",
        ]

    def update(self, instance, validated_data):
        instance.username = validated_data.get("username")
        instance.has_accepted_invite = True
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


class UserProfileSerializer(serializers.ModelSerializer):
    organization = OrganizationSerializer(read_only=True)
    role_label = serializers.CharField(source="get_role_label")

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "email",
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
