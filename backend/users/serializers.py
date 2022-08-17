from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from rest_framework.validators import UniqueValidator


# Serializer to Get User Details using Django Token Authentication
class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "username", "email", "first_name", "last_name", "username"]


# Serializer to Register User
class RegisterSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(
        required=True, validators=[UniqueValidator(queryset=User.objects.all())]
    )
    password = serializers.CharField(
        write_only=True, required=True, validators=[validate_password]
    )
    password2 = serializers.CharField(write_only=True, required=True)

    class Meta:
        model = User
        fields = (
            "username",
            "password",
            "password2",
            "email",
            "first_name",
            "last_name",
        )
        extra_kwargs = {
            "first_name": {"required": True},
            "last_name": {"required": True},
        }

    # Serializer functions
    def validate(self, attrs):
        if attrs["password"] != attrs["password2"]:
            raise serializers.ValidationError(
                {"password": "Password fields didn't match."}
            )
        return attrs

    def create(self, validated_data):
        user = User.objects.create(
            username=validated_data["username"],
            email=validated_data["email"],
            first_name=validated_data["first_name"],
            last_name=validated_data["last_name"],
        )
        user.set_password(validated_data["password"])
        user.save()
        return user


# Serializer to Login User
class LoginUserSerializer(serializers.Serializer):

    # Take the username or email as the input
    username = serializers.CharField(label="Username")
    password = serializers.CharField(label="Password")

    def validate(self, data):

        # Check if the username exists
        user = User.objects.filter(username=data["username"]).first()
        if user is None:
            # If not, check if it is an email address
            user = User.objects.filter(email=data["username"]).first()
        
        if user is None:
            raise serializers.ValidationError("User doesn't exist")

        # Check if the password is correct
        if not user.check_password(data["password"]):
            raise serializers.ValidationError("Incorrect password")

        return user
