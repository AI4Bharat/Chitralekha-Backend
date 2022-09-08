from django.db import models


class Video(models.Model):
    """
    Model for the Video object.
    """

    name = models.CharField(max_length=255, verbose_name="Video Name")
    url = models.URLField(unique=True, verbose_name="Video URL", db_index=True)
    duration = models.DurationField(verbose_name="Video Duration")
    subtitles = models.JSONField(verbose_name="Subtitles", null=True, blank=True)
    audio_only = models.BooleanField(
        verbose_name="Audio Only",
        default=False,
        help_text="Does this object only contain audio?",
    )

    def __str__(self):
        return self.name
