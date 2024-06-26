# Generated by Django 3.2.16 on 2023-03-02 15:14

import django.contrib.postgres.fields
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("organization", "0007_organization_default_voiceover_type"),
    ]

    operations = [
        migrations.AlterField(
            model_name="organization",
            name="default_task_types",
            field=django.contrib.postgres.fields.ArrayField(
                base_field=models.CharField(
                    blank=True,
                    choices=[
                        ("TRANSCRIPTION_EDIT", "Transcription Edit"),
                        ("TRANSCRIPTION_REVIEW", "Transcription Review"),
                        ("TRANSLATION_EDIT", "Translation Edit"),
                        ("TRANSLATION_REVIEW", "Translation Review"),
                        ("VOICEOVER_EDIT", "VoiceOver Edit"),
                    ],
                    default=None,
                    max_length=50,
                    null=True,
                ),
                blank=True,
                default=None,
                null=True,
                size=None,
                verbose_name="Organization Default Task Types",
            ),
        ),
    ]
