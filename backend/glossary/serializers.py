from rest_framework import serializers
from .models import Glossary
from django.contrib.auth import password_validation
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers


class GlossarySerializer(serializers.ModelSerializer):
    class Meta:
        model = Glossary
        fields = "__all__"
