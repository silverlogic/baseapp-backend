# Generated by Django 5.0.9 on 2024-12-17 05:08

import baseapp_comments.models
import baseapp_core.models
import baseapp_reports.models
import django.db.models.deletion
import django.utils.timezone
import model_utils.fields
import pgtrigger.compiler
import pgtrigger.migrations
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("contenttypes", "0002_remove_content_type_name"),
        ("pghistory", "0006_delete_aggregateevent"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
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
                ("blockers_count", models.PositiveIntegerField(default=0, editable=False)),
                ("blocking_count", models.PositiveIntegerField(default=0, editable=False)),
                ("followers_count", models.PositiveIntegerField(default=0, editable=False)),
                ("following_count", models.PositiveIntegerField(default=0, editable=False)),
                (
                    "reports_count",
                    models.JSONField(default=baseapp_reports.models.default_reports_count),
                ),
                (
                    "comments_count",
                    models.JSONField(
                        default=baseapp_comments.models.default_comments_count,
                        editable=False,
                        verbose_name="comments count",
                    ),
                ),
                (
                    "is_comments_enabled",
                    models.BooleanField(default=True, verbose_name="is comments enabled"),
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
                    "banner_image",
                    models.ImageField(
                        blank=True,
                        null=True,
                        upload_to=baseapp_core.models.random_name_in("profile_banner_images"),
                        verbose_name="banner image",
                    ),
                ),
                ("biography", models.TextField(blank=True, null=True, verbose_name="biography")),
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
                "abstract": False,
                "unique_together": {("target_content_type", "target_object_id")},
            },
        ),
        migrations.CreateModel(
            name="ProfileEvent",
            fields=[
                ("pgh_id", models.AutoField(primary_key=True, serialize=False)),
                ("pgh_created_at", models.DateTimeField(auto_now_add=True)),
                ("pgh_label", models.TextField(help_text="The event label.")),
                ("id", models.IntegerField()),
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
                ("blockers_count", models.PositiveIntegerField(default=0, editable=False)),
                ("blocking_count", models.PositiveIntegerField(default=0, editable=False)),
                ("followers_count", models.PositiveIntegerField(default=0, editable=False)),
                ("following_count", models.PositiveIntegerField(default=0, editable=False)),
                (
                    "reports_count",
                    models.JSONField(default=baseapp_reports.models.default_reports_count),
                ),
                (
                    "comments_count",
                    models.JSONField(
                        default=baseapp_comments.models.default_comments_count,
                        editable=False,
                        verbose_name="comments count",
                    ),
                ),
                (
                    "is_comments_enabled",
                    models.BooleanField(default=True, verbose_name="is comments enabled"),
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
                    "banner_image",
                    models.ImageField(
                        blank=True,
                        null=True,
                        upload_to=baseapp_core.models.random_name_in("profile_banner_images"),
                        verbose_name="banner image",
                    ),
                ),
                ("biography", models.TextField(blank=True, null=True, verbose_name="biography")),
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
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        related_name="+",
                        related_query_name="+",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="owner",
                    ),
                ),
                (
                    "pgh_context",
                    models.ForeignKey(
                        db_constraint=False,
                        null=True,
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        related_name="+",
                        to="pghistory.context",
                    ),
                ),
                (
                    "pgh_obj",
                    models.ForeignKey(
                        db_constraint=False,
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        related_name="events",
                        to=settings.BASEAPP_PROFILES_PROFILE_MODEL,
                    ),
                ),
                (
                    "target_content_type",
                    models.ForeignKey(
                        blank=True,
                        db_constraint=False,
                        null=True,
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        related_name="+",
                        related_query_name="+",
                        to="contenttypes.contenttype",
                        verbose_name="target content type",
                    ),
                ),
            ],
            options={
                "abstract": False,
            },
        ),
        pgtrigger.migrations.AddTrigger(
            model_name="profile",
            trigger=pgtrigger.compiler.Trigger(
                name="insert_insert",
                sql=pgtrigger.compiler.UpsertTriggerSql(
                    func='INSERT INTO "profiles_profileevent" ("banner_image", "biography", "blockers_count", "blocking_count", "comments_count", "created", "followers_count", "following_count", "id", "image", "is_comments_enabled", "modified", "name", "owner_id", "pgh_context_id", "pgh_created_at", "pgh_label", "pgh_obj_id", "reports_count", "status", "target_content_type_id", "target_object_id") VALUES (NEW."banner_image", NEW."biography", NEW."blockers_count", NEW."blocking_count", NEW."comments_count", NEW."created", NEW."followers_count", NEW."following_count", NEW."id", NEW."image", NEW."is_comments_enabled", NEW."modified", NEW."name", NEW."owner_id", _pgh_attach_context(), NOW(), \'insert\', NEW."id", NEW."reports_count", NEW."status", NEW."target_content_type_id", NEW."target_object_id"); RETURN NULL;',
                    hash="35958e2062305725d25e5ba8323a3a793c12c0d1",
                    operation="INSERT",
                    pgid="pgtrigger_insert_insert_87e8d",
                    table="profiles_profile",
                    when="AFTER",
                ),
            ),
        ),
        pgtrigger.migrations.AddTrigger(
            model_name="profile",
            trigger=pgtrigger.compiler.Trigger(
                name="update_update",
                sql=pgtrigger.compiler.UpsertTriggerSql(
                    condition="WHEN (OLD.* IS DISTINCT FROM NEW.*)",
                    func='INSERT INTO "profiles_profileevent" ("banner_image", "biography", "blockers_count", "blocking_count", "comments_count", "created", "followers_count", "following_count", "id", "image", "is_comments_enabled", "modified", "name", "owner_id", "pgh_context_id", "pgh_created_at", "pgh_label", "pgh_obj_id", "reports_count", "status", "target_content_type_id", "target_object_id") VALUES (NEW."banner_image", NEW."biography", NEW."blockers_count", NEW."blocking_count", NEW."comments_count", NEW."created", NEW."followers_count", NEW."following_count", NEW."id", NEW."image", NEW."is_comments_enabled", NEW."modified", NEW."name", NEW."owner_id", _pgh_attach_context(), NOW(), \'update\', NEW."id", NEW."reports_count", NEW."status", NEW."target_content_type_id", NEW."target_object_id"); RETURN NULL;',
                    hash="06c26cce939a455354b6c6fbba8f509f555cd59c",
                    operation="UPDATE",
                    pgid="pgtrigger_update_update_c0aea",
                    table="profiles_profile",
                    when="AFTER",
                ),
            ),
        ),
        pgtrigger.migrations.AddTrigger(
            model_name="profile",
            trigger=pgtrigger.compiler.Trigger(
                name="delete_delete",
                sql=pgtrigger.compiler.UpsertTriggerSql(
                    func='INSERT INTO "profiles_profileevent" ("banner_image", "biography", "blockers_count", "blocking_count", "comments_count", "created", "followers_count", "following_count", "id", "image", "is_comments_enabled", "modified", "name", "owner_id", "pgh_context_id", "pgh_created_at", "pgh_label", "pgh_obj_id", "reports_count", "status", "target_content_type_id", "target_object_id") VALUES (OLD."banner_image", OLD."biography", OLD."blockers_count", OLD."blocking_count", OLD."comments_count", OLD."created", OLD."followers_count", OLD."following_count", OLD."id", OLD."image", OLD."is_comments_enabled", OLD."modified", OLD."name", OLD."owner_id", _pgh_attach_context(), NOW(), \'delete\', OLD."id", OLD."reports_count", OLD."status", OLD."target_content_type_id", OLD."target_object_id"); RETURN NULL;',
                    hash="40d2dd5b074905dd9baef7d09ef7b54a5aff9f1d",
                    operation="DELETE",
                    pgid="pgtrigger_delete_delete_4fa3e",
                    table="profiles_profile",
                    when="AFTER",
                ),
            ),
        ),
    ]