# Generated by Django 3.2.16 on 2022-11-29 11:29

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("task", "0002_auto_20221129_0903"),
    ]

    operations = [
        migrations.AlterField(
            model_name="task",
            name="eta",
            field=models.DateTimeField(
                blank=True, default=None, null=True, verbose_name="ETA"
            ),
        ),
    ]
