# Generated by Django 3.2.16 on 2022-11-29 11:29

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("video", "0009_video_language"),
    ]

    operations = [
        migrations.AddField(
            model_name="video",
            name="description",
            field=models.TextField(
                blank=True, help_text="Video Description", max_length=400, null=True
            ),
        ),
    ]
