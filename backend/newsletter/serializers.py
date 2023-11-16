from rest_framework import serializers
from .models import Newsletter


class NewsletterSerializer(serializers.ModelSerializer):
    category = serializers.ListField()
    class Meta:
        model = Newsletter
        fields = ("newsletter_uuid", "submitter_id", "content", "category")
