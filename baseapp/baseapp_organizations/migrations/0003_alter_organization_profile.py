# Generated by Django 5.0.1 on 2025-04-03 13:23

import django.db.models.deletion
import swapper
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("baseapp_organizations", "0002_organization_name"),
        swapper.dependency("baseapp_profiles", "Profile"),
    ]

    operations = [
        migrations.AlterField(
            model_name="organization",
            name="profile",
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="%(class)s",
                to=swapper.get_model_name("baseapp_profiles", "Profile"),
                verbose_name="profile",
            ),
        ),
    ]
