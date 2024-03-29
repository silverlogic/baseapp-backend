# Generated by Django 4.2.7 on 2024-02-01 15:18

from django.contrib.postgres.operations import CITextExtension
from django.db import migrations

import baseapp_message_templates.models


class Migration(migrations.Migration):

    dependencies = [
        ("baseapp_message_templates", "0002_auto_20240108_1503"),
    ]

    operations = [
        CITextExtension(),
        migrations.AlterField(
            model_name="emailtemplate",
            name="name",
            field=baseapp_message_templates.models.CaseInsensitiveCharField(
                help_text="Unique name used to identify this message", max_length=255, unique=True
            ),
        ),
        migrations.AlterField(
            model_name="smstemplate",
            name="name",
            field=baseapp_message_templates.models.CaseInsensitiveCharField(
                help_text="Unique name used to identify this message", max_length=255, unique=True
            ),
        ),
    ]
