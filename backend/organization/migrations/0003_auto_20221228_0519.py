# Generated by Django 3.2.16 on 2022-12-28 05:19

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("organization", "0002_invite"),
    ]

    operations = [
        migrations.AddField(
            model_name="organization",
            name="default_transcript_editor",
            field=models.ForeignKey(
                default=None,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="transcript_editor",
                to=settings.AUTH_USER_MODEL,
                verbose_name="transcript editor",
            ),
        ),
        migrations.AddField(
            model_name="organization",
            name="default_transcript_reviewer",
            field=models.ForeignKey(
                default=None,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="transcript_reviewer",
                to=settings.AUTH_USER_MODEL,
                verbose_name="transcript reviewer",
            ),
        ),
        migrations.AddField(
            model_name="organization",
            name="default_transcript_type",
            field=models.CharField(
                blank=True,
                choices=[
                    ("ORIGINAL_SOURCE", "Original Source"),
                    ("MACHINE_GENERATED", "Machine Generated"),
                    ("MANUALLY_CREATED", "Manually Created"),
                ],
                default=None,
                max_length=35,
                null=True,
                verbose_name="default transcript type",
            ),
        ),
        migrations.AddField(
            model_name="organization",
            name="default_translation_editor",
            field=models.ForeignKey(
                default=None,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="translation_editor",
                to=settings.AUTH_USER_MODEL,
                verbose_name="translation editor",
            ),
        ),
        migrations.AddField(
            model_name="organization",
            name="default_translation_reviewer",
            field=models.ForeignKey(
                default=None,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="translation_reviewer",
                to=settings.AUTH_USER_MODEL,
                verbose_name="translation reviewer",
            ),
        ),
        migrations.AddField(
            model_name="organization",
            name="default_translation_type",
            field=models.CharField(
                blank=True,
                choices=[
                    ("MACHINE_GENERATED", "Machine Generated"),
                    ("MANUALLY_CREATED", "Manually Created"),
                ],
                default=None,
                max_length=35,
                null=True,
                verbose_name="Default Translation Type",
            ),
        ),
        migrations.AlterField(
            model_name="organization",
            name="created_by",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="organization_created",
                to=settings.AUTH_USER_MODEL,
                verbose_name="created_by",
            ),
        ),
    ]
