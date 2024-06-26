# Generated by Django 3.2.16 on 2022-12-28 05:19

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("project", "0003_alter_project_managers"),
    ]

    operations = [
        migrations.AddField(
            model_name="project",
            name="default_transcript_editor",
            field=models.ForeignKey(
                default=None,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="project_default_transcript_editor",
                to=settings.AUTH_USER_MODEL,
                verbose_name="Project Default Transcript Editor",
            ),
        ),
        migrations.AddField(
            model_name="project",
            name="default_transcript_reviewer",
            field=models.ForeignKey(
                default=None,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="project_default_transcript_reviewer",
                to=settings.AUTH_USER_MODEL,
                verbose_name="Project Default Transcript Reviewer",
            ),
        ),
        migrations.AddField(
            model_name="project",
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
                verbose_name="Project Default Transcript Type",
            ),
        ),
        migrations.AddField(
            model_name="project",
            name="default_translation_editor",
            field=models.ForeignKey(
                default=None,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="project_default_translation_editor",
                to=settings.AUTH_USER_MODEL,
                verbose_name="Project Default Translation Editor",
            ),
        ),
        migrations.AddField(
            model_name="project",
            name="default_translation_reviewer",
            field=models.ForeignKey(
                default=None,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="project_default_translation_reviewer",
                to=settings.AUTH_USER_MODEL,
                verbose_name="Project Default Translation Reviewer",
            ),
        ),
        migrations.AddField(
            model_name="project",
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
                verbose_name="Project Default Translation Type",
            ),
        ),
    ]
