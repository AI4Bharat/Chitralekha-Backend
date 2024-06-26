# Generated by Django 3.2.16 on 2023-05-29 11:46

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("project", "0008_alter_project_default_task_types"),
    ]

    operations = [
        migrations.AlterField(
            model_name="project",
            name="default_transcript_type",
            field=models.CharField(
                blank=True,
                choices=[
                    ("ORIGINAL_SOURCE", "Original Source"),
                    ("MACHINE_GENERATED", "Machine Generated"),
                    ("MANUALLY_CREATED", "Manually Created"),
                    ("MANUALLY_UPLOADED", "Manually Uploaded"),
                ],
                default=None,
                max_length=35,
                null=True,
                verbose_name="Project Default Transcript Type",
            ),
        ),
    ]
