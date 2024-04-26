# Generated by Django 3.2.16 on 2022-10-12 16:04

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("project", "0001_initial"),
        ("video", "0007_video_audio_only"),
    ]

    operations = [
        migrations.AddField(
            model_name="video",
            name="project_id",
            field=models.ForeignKey(
                help_text="Organization to which the Project belongs",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                to="project.project",
            ),
        ),
    ]