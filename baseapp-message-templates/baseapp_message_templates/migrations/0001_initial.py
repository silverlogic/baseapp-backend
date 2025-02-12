# Generated by Django 3.2.18 on 2023-05-23 16:26

import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models

import ckeditor.fields
import model_utils.fields
from baseapp_message_templates.utils import random_name_in


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="EmailTemplate",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "created",
                    model_utils.fields.AutoCreatedField(
                        default=django.utils.timezone.now,
                        editable=False,
                        verbose_name="created",
                    ),
                ),
                (
                    "modified",
                    model_utils.fields.AutoLastModifiedField(
                        default=django.utils.timezone.now,
                        editable=False,
                        verbose_name="modified",
                    ),
                ),
                (
                    "name",
                    models.CharField(
                        help_text="Unique name used to identify this message",
                        max_length=255,
                        unique=True,
                    ),
                ),
                (
                    "sendgrid_template_id",
                    models.CharField(blank=True, max_length=255, null=True),
                ),
                (
                    "subject",
                    models.CharField(
                        blank=True,
                        help_text="Email subject line",
                        max_length=255,
                        null=True,
                    ),
                ),
                (
                    "html_content",
                    ckeditor.fields.RichTextField(
                        blank=True,
                        help_text="Text that will be inputted into Template html version",
                        null=True,
                    ),
                ),
                (
                    "plain_text_content",
                    ckeditor.fields.RichTextField(
                        blank=True,
                        help_text="Text that will be inputted into Template plain text version",
                    ),
                ),
            ],
            options={
                "ordering": ["-name"],
            },
        ),
        migrations.CreateModel(
            name="Attachment",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "created",
                    model_utils.fields.AutoCreatedField(
                        default=django.utils.timezone.now,
                        editable=False,
                        verbose_name="created",
                    ),
                ),
                (
                    "modified",
                    model_utils.fields.AutoLastModifiedField(
                        default=django.utils.timezone.now,
                        editable=False,
                        verbose_name="modified",
                    ),
                ),
                (
                    "file",
                    models.FileField(
                        upload_to=random_name_in("copy_template_file"),
                    ),
                ),
                ("filename", models.CharField(blank=True, max_length=255, null=True)),
                (
                    "template",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="static_attachments",
                        to="baseapp_message_templates.emailtemplate",
                    ),
                ),
            ],
            options={
                "abstract": False,
            },
        ),
    ]
