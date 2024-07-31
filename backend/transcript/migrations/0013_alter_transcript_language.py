# Generated by Django 3.2.16 on 2023-06-09 08:38

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("transcript", "0012_alter_transcript_transcript_type"),
    ]

    operations = [
        migrations.AlterField(
            model_name="transcript",
            name="language",
            field=models.CharField(
                choices=[
                    ("en", "English"),
                    ("hi", "Hindi"),
                    ("as", "Assamese"),
                    ("bn", "Bengali"),
                    ("gu", "Gujarati"),
                    ("kn", "Kannada"),
                    ("ml", "Malayalam"),
                    ("mr", "Marathi"),
                    ("or", "Oriya"),
                    ("pa", "Punjabi"),
                    ("te", "Telugu"),
                ],
                default="en",
                max_length=10,
                verbose_name="Transcript Language",
            ),
        ),
    ]