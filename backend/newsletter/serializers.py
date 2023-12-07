from rest_framework import serializers
from .models import Newsletter, SubscribedUsers
from django.db import migrations, models


class NewsletterSerializer(serializers.ModelSerializer):
    content = serializers.ListField(child=serializers.DictField())

    class Meta:
        model = Newsletter
        fields = ("newsletter_uuid", "submitter_id", "content", "category")

class SubscribedUsersSerializers(serializers.ModelSerializer):
    class Meta:
        model = SubscribedUsers
        fields = ("user")
