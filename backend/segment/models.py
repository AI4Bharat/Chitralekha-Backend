import uuid
from django.db import models
from django.utils import timezone
from voiceover.models import VoiceOver

def parse_time_string_to_seconds(time_str):
    if not isinstance(time_str, str):
        return None
    try:
        parts = time_str.split(':')
        if len(parts) == 3:
            hours = int(parts[0])
            minutes = int(parts[1])
            seconds_ms = float(parts[2])
            return hours * 3600 + minutes * 60 + seconds_ms
        else:
            return None
    except ValueError:
        return None

class Segment(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        help_text="Unique identifier for the segment."
    )
    voiceover_object = models.ForeignKey(
        VoiceOver,
        on_delete=models.CASCADE,
        related_name='segments',
        help_text="The Voiceover object this segment belongs to."
    )
    order_key = models.FloatField(
        help_text="Floating-point number used for sequential ordering of segments within a VO object."
    )
    text = models.TextField(
        blank=True,
        null=True,
        help_text="The translated text."
    )
    transcription_text = models.TextField(
        blank=True,
        null=True,
        help_text="The original transcription text."
    )
    start_time = models.CharField(
        max_length=12,
        help_text="Start time of the segment in 'HH:MM:SS.mmm' string format."
    )
    end_time = models.CharField(
        max_length=12,
        help_text="End time of the segment in 'HH:MM:SS.mmm' string format."
    )
    duration = models.FloatField(
        help_text="Calculated duration of the segment in seconds (end_time - start_time)."
    )
    audio_url = models.URLField(
        max_length=500,
        blank=True,
        null=True,
        help_text="URL to the generated voiceover audio file."
    )
    image_url = models.URLField(
        max_length=500,
        blank=True,
        null=True,
        help_text="URL to a generated thumbnail for this segment."
    )
    audio_speed = models.FloatField(
        default=1.0,
        help_text="Playback speed of the generated audio."
    )
    audio_generated = models.BooleanField(
        default=False,
        help_text="Denotes if audio voiceover has been successfully generated for this segment."
    )

    class Meta:
        verbose_name = "Segment"
        verbose_name_plural = "Segments"
        ordering = ['order_key']
        unique_together = ('voiceover_object', 'order_key')

    def __str__(self):
        return "VO Segment: " + str(self.voiceover_object.voice_over_uuid) + str(self.id)
    
    def save(self, *args, **kwargs):
        """
        Overrides the default save method to auto-calculate duration before saving.
        """
        start_seconds = parse_time_string_to_seconds(self.start_time)
        end_seconds = parse_time_string_to_seconds(self.end_time)

        if start_seconds is not None and end_seconds is not None:
            self.duration = end_seconds - start_seconds
        else:
            self.duration = -1

        super().save(*args, **kwargs)
