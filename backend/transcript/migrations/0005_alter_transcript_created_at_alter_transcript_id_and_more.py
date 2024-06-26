# Generated by Django 4.0.5 on 2022-07-13 17:05

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("video", "0003_video_subtitles"),
        ("transcript", "0004_alter_transcript_language"),
    ]

    operations = [
        migrations.AlterField(
            model_name="transcript",
            name="created_at",
            field=models.DateTimeField(
                auto_now_add=True, verbose_name="Transcript Created At"
            ),
        ),
        migrations.AlterField(
            model_name="transcript",
            name="id",
            field=models.UUIDField(
                default=uuid.uuid4,
                editable=False,
                primary_key=True,
                serialize=False,
                verbose_name="Transcript ID",
            ),
        ),
        migrations.AlterField(
            model_name="transcript",
            name="language",
            field=models.CharField(
                choices=[("en", "English"), ("hi", "Hindi")],
                default="en",
                max_length=2,
                verbose_name="Transcript Language",
            ),
        ),
        migrations.AlterField(
            model_name="transcript",
            name="parent_transcript",
            field=models.ForeignKey(
                blank=True,
                default=None,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                to="transcript.transcript",
                verbose_name="Parent Transcript",
            ),
        ),
        migrations.AlterField(
            model_name="transcript",
            name="payload",
            field=models.JSONField(verbose_name="Transcription Output"),
        ),
        migrations.AlterField(
            model_name="transcript",
            name="transcript_type",
            field=models.CharField(
                choices=[
                    ("os", "Original Source"),
                    ("uos", "Updated Original Source"),
                    ("mg", "Machine Generated"),
                    ("umg", "Updated Machine Generated"),
                ],
                default="mg",
                max_length=3,
                verbose_name="Transcript Type",
            ),
        ),
        migrations.AlterField(
            model_name="transcript",
            name="updated_at",
            field=models.DateTimeField(
                auto_now=True, verbose_name="Transcript Updated At"
            ),
        ),
        migrations.AlterField(
            model_name="transcript",
            name="user",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                to=settings.AUTH_USER_MODEL,
                verbose_name="Transcriptor",
            ),
        ),
        migrations.AlterField(
            model_name="transcript",
            name="video",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="transcripts",
                to="video.video",
                verbose_name="Transcript Video ID",
            ),
        ),
    ]
