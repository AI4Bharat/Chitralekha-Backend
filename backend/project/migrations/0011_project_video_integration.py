# Generated by Django 3.2.16 on 2023-07-21 07:34

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("project", "0010_alter_project_default_target_languages"),
    ]

    operations = [
        migrations.AddField(
            model_name="project",
            name="video_integration",
            field=models.BooleanField(
                default=False,
                help_text="Indicates whether video integration is needed for VO tasks or not.",
                verbose_name="require_video_integration",
            ),
        ),
    ]
