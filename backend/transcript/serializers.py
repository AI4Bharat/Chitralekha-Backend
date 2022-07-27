from rest_framework.serializers import ModelSerializer

from .models import Transcript

class TranscriptSerializer(ModelSerializer):

    class Meta:
        model = Transcript
        fields = "__all__"