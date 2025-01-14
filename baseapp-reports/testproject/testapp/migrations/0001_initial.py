# Generated by Django 4.2.10 on 2024-03-19 14:36

import baseapp_core.models
import baseapp_reports.models
import django.utils.timezone
import phonenumber_field.modelfields
from django.contrib.postgres.operations import CITextExtension
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        CITextExtension(),
        migrations.CreateModel(
            name="User",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("password", models.CharField(max_length=128, verbose_name="password")),
                (
                    "last_login",
                    models.DateTimeField(blank=True, null=True, verbose_name="last login"),
                ),
                (
                    "is_superuser",
                    models.BooleanField(
                        default=False,
                        help_text="Designates that this user has all permissions without explicitly assigning them.",
                        verbose_name="superuser status",
                    ),
                ),
                (
                    "email",
                    baseapp_core.models.CaseInsensitiveEmailField(
                        db_index=True, max_length=254, unique=True
                    ),
                ),
                ("is_email_verified", models.BooleanField(default=False)),
                (
                    "date_joined",
                    models.DateTimeField(
                        default=django.utils.timezone.now, verbose_name="date joined"
                    ),
                ),
                (
                    "password_changed_date",
                    models.DateTimeField(
                        default=django.utils.timezone.now,
                        verbose_name="last date password was changed",
                    ),
                ),
                (
                    "new_email",
                    baseapp_core.models.CaseInsensitiveEmailField(blank=True, max_length=254),
                ),
                (
                    "is_new_email_confirmed",
                    models.BooleanField(
                        default=False, help_text="Has the user confirmed they want an email change?"
                    ),
                ),
                ("first_name", models.CharField(blank=True, max_length=100)),
                ("last_name", models.CharField(blank=True, max_length=100)),
                (
                    "phone_number",
                    phonenumber_field.modelfields.PhoneNumberField(
                        blank=True, max_length=128, null=True, region=None, unique=True
                    ),
                ),
                (
                    "is_active",
                    models.BooleanField(
                        default=True,
                        help_text="Designates whether this user should be treated as active. Unselect this instead of deleting accounts.",
                        verbose_name="active",
                    ),
                ),
                (
                    "is_staff",
                    models.BooleanField(
                        default=False,
                        help_text="Designates whether the user can log into this admin site.",
                        verbose_name="staff status",
                    ),
                ),
                (
                    "reports_count",
                    models.JSONField(default=baseapp_reports.models.default_reports_count),
                ),
                (
                    "groups",
                    models.ManyToManyField(
                        blank=True,
                        help_text="The groups this user belongs to. A user will get all permissions granted to each of their groups.",
                        related_name="user_set",
                        related_query_name="user",
                        to="auth.group",
                        verbose_name="groups",
                    ),
                ),
                (
                    "user_permissions",
                    models.ManyToManyField(
                        blank=True,
                        help_text="Specific permissions for this user.",
                        related_name="user_set",
                        related_query_name="user",
                        to="auth.permission",
                        verbose_name="user permissions",
                    ),
                ),
            ],
            options={
                "verbose_name": "user",
                "verbose_name_plural": "users",
                "permissions": [
                    ("view_all_users", "can view all users"),
                    ("view_user_email", "can view user's email field"),
                    ("view_user_phone_number", "can view user's phone number field"),
                    ("view_user_is_superuser", "can view user's is_superuser field"),
                    ("view_user_is_staff", "can view user's is_staff field"),
                    ("view_user_is_email_verified", "can view user's is_email_verified field"),
                    (
                        "view_user_password_changed_date",
                        "can view user's password_changed_date field",
                    ),
                    ("view_user_new_email", "can view user's new_email field"),
                    (
                        "view_user_is_new_email_confirmed",
                        "can view user's is_new_email_confirmed field",
                    ),
                ],
                "abstract": False,
            },
        ),
    ]
