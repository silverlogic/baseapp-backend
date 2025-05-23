# Generated by Django 5.0.11 on 2025-02-21 03:39

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("baseapp_payments", "0003_delete_plan"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [
        migrations.CreateModel(
            name="Subscription",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("remote_customer_id", models.CharField(max_length=255)),
                ("remote_subscription_id", models.CharField(max_length=255)),
            ],
            options={
                "swappable": "BASEAPP_PAYMENTS_SUBSCRIPTION_MODEL",
                "unique_together": {("remote_customer_id", "remote_subscription_id")},
            },
        ),
        migrations.CreateModel(
            name="Customer",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("entity_id", models.PositiveIntegerField()),
                ("remote_customer_id", models.CharField(max_length=255)),
                (
                    "entity_type",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, to="contenttypes.contenttype"
                    ),
                ),
            ],
            options={
                "swappable": "BASEAPP_PAYMENTS_CUSTOMER_MODEL",
                "unique_together": {("entity_type", "entity_id")},
            },
        ),
    ]
