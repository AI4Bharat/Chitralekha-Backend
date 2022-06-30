from django.db import models


class Video(models.Model):
    '''
    Model for the Video object.
    '''
    name = models.CharField(max_length=255, verbose_name="Video Name")
    url = models.URLField(unique=True, verbose_name="Video URL", db_index=True)
    duration = models.DurationField(verbose_name="Video Duration")

    def __str__(self):
        return self.name
