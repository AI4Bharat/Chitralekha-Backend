# Generated by Django 3.2.16 on 2023-05-17 09:53

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0007_alter_user_role"),
    ]

    operations = [
        migrations.AlterField(
            model_name="user",
            name="phone",
            field=models.CharField(
                blank=True, max_length=256, null=True, verbose_name="phone"
            ),
        ),
    ]
