# Generated by Django 3.2.16 on 2023-05-17 10:36

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("organization", "0010_alter_organization_title"),
    ]

    operations = [
        migrations.AlterField(
            model_name="organization",
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
                verbose_name="default transcript type",
            ),
        ),
    ]