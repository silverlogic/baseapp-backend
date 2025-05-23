# Generated by Django 5.1.3 on 2024-11-29 18:04

import django.db.models.deletion
import django.utils.timezone
import model_utils.fields
import swapper
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        swapper.dependency("baseapp_profiles", "Profile"),
        swapper.dependency("baseapp_organizations", "Organization"),
    ]

    operations = [
        migrations.CreateModel(
            name="Organization",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                (
                    "created",
                    model_utils.fields.AutoCreatedField(
                        default=django.utils.timezone.now, editable=False, verbose_name="created"
                    ),
                ),
                (
                    "modified",
                    model_utils.fields.AutoLastModifiedField(
                        default=django.utils.timezone.now, editable=False, verbose_name="modified"
                    ),
                ),
                (
                    "profile",
                    models.OneToOneField(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="%(class)s",
                        to=swapper.get_model_name("baseapp_profiles", "Profile"),
                        verbose_name="profile",
                    ),
                ),
            ],
            options={
                "verbose_name": "organization",
                "verbose_name_plural": "organizations",
                "abstract": False,
                "swappable": swapper.swappable_setting("baseapp_organizations", "Organization"),
            },
        ),
    ]
