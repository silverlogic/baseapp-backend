# Generated by Django 3.2.16 on 2023-01-10 17:42

import django.contrib.auth.models
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("auth", "0012_alter_user_first_name_max_length"),
        ("baseapp_drf_view_action_permissions", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="TestModel",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("title", models.CharField(blank=True, max_length=50)),
            ],
            options={
                "permissions": [
                    ("view_testmodel_list", "Can List all testmodel"),
                    ("test_disable", "Can disable test"),
                    ("list_tests", "Can list tests"),
                    ("custom_action_testmodel", "Can custom action testmodel"),
                    (
                        "custom_detail_action_testmodel",
                        "Can custom detail action testmodel",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="User",
            fields=[
                (
                    "user_ptr",
                    models.OneToOneField(
                        auto_created=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        parent_link=True,
                        primary_key=True,
                        serialize=False,
                        to="auth.user",
                    ),
                ),
                (
                    "exclude_permissions",
                    models.ManyToManyField(
                        blank=True,
                        related_name="excluded_permission_users",
                        to="auth.Permission",
                    ),
                ),
                (
                    "role",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="users",
                        to="baseapp_drf_view_action_permissions.role",
                    ),
                ),
            ],
            options={
                "verbose_name": "user",
                "verbose_name_plural": "users",
                "abstract": False,
            },
            bases=("auth.user", models.Model),
            managers=[
                ("objects", django.contrib.auth.models.UserManager()),
            ],
        ),
    ]
