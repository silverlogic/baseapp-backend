# Generated by Django 5.1.2 on 2025-01-08 10:20

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("testapp", "0011_user_profile"),
        migrations.swappable_dependency(settings.BASEAPP_PROFILES_PROFILE_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name="user",
            name="profile",
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="%(class)s",
                to=settings.BASEAPP_PROFILES_PROFILE_MODEL,
                verbose_name="profile",
            ),
        ),
    ]
