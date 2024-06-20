# Generated by Django 5.0.1 on 2024-06-04 23:01
import baseapp_core.models
import django.db.models.deletion
import django.utils.timezone
import model_utils.fields
import swapper
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("contenttypes", "0002_remove_content_type_name"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        swapper.dependency("baseapp_profiles", "Profile"),
        swapper.dependency("baseapp_profiles", "ProfileUserRole"),
    ]

    operations = [
        migrations.CreateModel(
            name="Profile",
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
                    "name",
                    models.CharField(blank=True, max_length=255, null=True, verbose_name="name"),
                ),
                (
                    "image",
                    models.ImageField(
                        blank=True,
                        null=True,
                        upload_to=baseapp_core.models.random_name_in("profile_images"),
                        verbose_name="image",
                    ),
                ),
                (
                    "target_object_id",
                    models.PositiveIntegerField(
                        blank=True, null=True, verbose_name="target object id"
                    ),
                ),
                ("status", models.IntegerField(choices=[(1, "public"), (2, "private")], default=1)),
                (
                    "owner",
                    models.ForeignKey(
                        db_constraint=False,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="profiles_owner",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="owner",
                    ),
                ),
                (
                    "target_content_type",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="profiles",
                        to="contenttypes.contenttype",
                        verbose_name="target content type",
                    ),
                ),
            ],
            options={
                "permissions": [("use_profile", "can use profile")],
                "swappable": swapper.swappable_setting("baseapp_profiles", "Profile"),
                "unique_together": {("target_content_type", "target_object_id")},
            },
        ),
        migrations.CreateModel(
            name="ProfileUserRole",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("role", models.IntegerField(choices=[(1, "admin"), (2, "manager")], default=2)),
                (
                    "profile",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="members",
                        to=swapper.get_model_name("baseapp_profiles", "Profile"),
                        verbose_name="profile",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="profile_members",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="user",
                    ),
                ),
            ],
            options={
                "swappable": swapper.swappable_setting("baseapp_profiles", "ProfileUserRole"),
                "unique_together": {("user", "profile")},
            },
        ),
    ]