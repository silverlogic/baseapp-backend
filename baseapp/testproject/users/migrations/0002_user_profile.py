# Generated by Django 5.0.1 on 2025-04-01 17:35

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0001_initial"),
        migrations.swappable_dependency(settings.BASEAPP_PROFILES_PROFILE_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="profile",
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="%(class)s",
                to=settings.BASEAPP_PROFILES_PROFILE_MODEL,
                verbose_name="profile",
            ),
        ),
    ]
