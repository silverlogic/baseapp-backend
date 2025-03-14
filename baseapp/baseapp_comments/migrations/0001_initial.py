# Generated by Django 4.2.10 on 2024-02-18 19:19

import django.db.models.deletion
import django.utils.timezone
import model_utils.fields
import pgtrigger.compiler
import pgtrigger.migrations
import swapper
from django.conf import settings
from django.db import migrations, models

import baseapp_comments.models
import baseapp_comments.validators
import baseapp_reactions.models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("contenttypes", "0002_remove_content_type_name"),
        ("pghistory", "0005_events_middlewareevents"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        swapper.dependency("baseapp_comments", "Comment"),
    ]

    operations = [
        migrations.CreateModel(
            name="Comment",
            fields=[
                (
                    "id",
                    models.BigAutoField(
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
                    "reactions_count",
                    models.JSONField(default=baseapp_reactions.models.default_reactions_count),
                ),
                (
                    "comments_count",
                    models.JSONField(
                        default=baseapp_comments.models.default_comments_count,
                        verbose_name="comments count",
                    ),
                ),
                (
                    "is_comments_enabled",
                    models.BooleanField(default=True, verbose_name="is comments enabled"),
                ),
                (
                    "profile_object_id",
                    models.PositiveIntegerField(
                        blank=True, db_index=True, null=True, verbose_name="profile object id"
                    ),
                ),
                (
                    "body",
                    models.TextField(
                        blank=True,
                        null=True,
                        validators=[baseapp_comments.validators.blocked_words_validator],
                        verbose_name="body",
                    ),
                ),
                (
                    "language",
                    models.CharField(
                        blank=True,
                        help_text="languaged used in the comment",
                        max_length=10,
                        null=True,
                        verbose_name="language",
                    ),
                ),
                ("is_edited", models.BooleanField(default=False, verbose_name="is edited")),
                ("is_pinned", models.BooleanField(default=False, verbose_name="is pinned")),
                (
                    "target_object_id",
                    models.PositiveIntegerField(
                        blank=True, db_index=True, null=True, verbose_name="target object id"
                    ),
                ),
                (
                    "status",
                    models.IntegerField(
                        choices=[(0, "deleted"), (1, "published")],
                        db_index=True,
                        default=1,
                        verbose_name="status",
                    ),
                ),
                (
                    "in_reply_to",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="comments",
                        to=swapper.get_model_name("baseapp_comments", "Comment"),
                        verbose_name="in reply to",
                    ),
                ),
                (
                    "profile_content_type",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="comments_outbox",
                        to="contenttypes.contenttype",
                        verbose_name="profile content type",
                    ),
                ),
                (
                    "target_content_type",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="comments_inbox",
                        to="contenttypes.contenttype",
                        verbose_name="target content type",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="comments",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="user",
                    ),
                ),
            ],
            options={
                "swappable": swapper.swappable_setting("baseapp_comments", "Comment"),
                "verbose_name": "comment",
                "verbose_name_plural": "comments",
                "ordering": ["-is_pinned", "-created"],
                "permissions": [
                    ("pin_comment", "can pin comments"),
                    ("report_comment", "can report comments"),
                    ("view_all_comments", "can view all comments"),
                ],
            },
        ),
        migrations.CreateModel(
            name="CommentEvent",
            fields=[
                ("pgh_id", models.AutoField(primary_key=True, serialize=False)),
                (
                    "pgh_operation",
                    models.IntegerField(
                        choices=[
                            (1, "Insert"),
                            (2, "Update"),
                            (3, "Delete"),
                            (4, "Insertorupdate"),
                        ],
                        null=True,
                    ),
                ),
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
                (
                    "is_comments_enabled",
                    models.BooleanField(default=True, verbose_name="is comments enabled"),
                ),
                (
                    "profile_object_id",
                    models.PositiveIntegerField(
                        blank=True, null=True, verbose_name="profile object id"
                    ),
                ),
                (
                    "body",
                    models.TextField(
                        blank=True,
                        null=True,
                        validators=[baseapp_comments.validators.blocked_words_validator],
                        verbose_name="body",
                    ),
                ),
                (
                    "language",
                    models.CharField(
                        blank=True,
                        help_text="languaged used in the comment",
                        max_length=10,
                        null=True,
                        verbose_name="language",
                    ),
                ),
                ("is_edited", models.BooleanField(default=False, verbose_name="is edited")),
                ("is_pinned", models.BooleanField(default=False, verbose_name="is pinned")),
                (
                    "target_object_id",
                    models.PositiveIntegerField(
                        blank=True, null=True, verbose_name="target object id"
                    ),
                ),
                (
                    "status",
                    models.IntegerField(
                        choices=[(0, "deleted"), (1, "published")], default=1, verbose_name="status"
                    ),
                ),
                (
                    "in_reply_to",
                    models.ForeignKey(
                        blank=True,
                        db_constraint=False,
                        null=True,
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        related_name="+",
                        related_query_name="+",
                        to=swapper.get_model_name("baseapp_comments", "Comment"),
                        verbose_name="in reply to",
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
                        related_name="event",
                        to="baseapp_comments.comment",
                    ),
                ),
                (
                    "profile_content_type",
                    models.ForeignKey(
                        blank=True,
                        db_constraint=False,
                        null=True,
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        related_name="+",
                        related_query_name="+",
                        to="contenttypes.contenttype",
                        verbose_name="profile content type",
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
                (
                    "user",
                    models.ForeignKey(
                        blank=True,
                        db_constraint=False,
                        null=True,
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        related_name="+",
                        related_query_name="+",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="user",
                    ),
                ),
            ],
            options={
                "abstract": False,
            },
        ),
        migrations.AddIndex(
            model_name="comment",
            index=models.Index(
                fields=[
                    "target_content_type",
                    "target_object_id",
                    "status",
                    "-is_pinned",
                    "-created",
                ],
                name="baseapp_com_target__7c13ac_idx",
            ),
        ),
        pgtrigger.migrations.AddTrigger(
            model_name="comment",
            trigger=pgtrigger.compiler.Trigger(
                name="soft_delete",
                sql=pgtrigger.compiler.UpsertTriggerSql(
                    func='UPDATE "baseapp_comments_comment" SET status = 0 WHERE "id" = OLD."id"; RETURN NULL;',
                    hash="f62a42fafa429eaa2c0ea7e869672d9f49195e10",
                    operation="DELETE",
                    pgid="pgtrigger_soft_delete_e373f",
                    table="baseapp_comments_comment",
                    when="BEFORE",
                ),
            ),
        ),
        pgtrigger.migrations.AddTrigger(
            model_name="comment",
            trigger=pgtrigger.compiler.Trigger(
                name="snapshot_insert",
                sql=pgtrigger.compiler.UpsertTriggerSql(
                    func='INSERT INTO "baseapp_comments_commentevent" ("body", "created", "id", "in_reply_to_id", "is_comments_enabled", "is_edited", "is_pinned", "language", "modified", "pgh_context_id", "pgh_created_at", "pgh_label", "pgh_obj_id", "pgh_operation", "profile_content_type_id", "profile_object_id", "status", "target_content_type_id", "target_object_id", "user_id") VALUES (NEW."body", NEW."created", NEW."id", NEW."in_reply_to_id", NEW."is_comments_enabled", NEW."is_edited", NEW."is_pinned", NEW."language", NEW."modified", _pgh_attach_context(), NOW(), \'snapshot\', NEW."id", 1, NEW."profile_content_type_id", NEW."profile_object_id", NEW."status", NEW."target_content_type_id", NEW."target_object_id", NEW."user_id"); RETURN NULL;',
                    hash="922e9dedb51a29890cc61ea85f30c844b4c122b5",
                    operation="INSERT",
                    pgid="pgtrigger_snapshot_insert_32a4a",
                    table="baseapp_comments_comment",
                    when="AFTER",
                ),
            ),
        ),
        pgtrigger.migrations.AddTrigger(
            model_name="comment",
            trigger=pgtrigger.compiler.Trigger(
                name="snapshot_update",
                sql=pgtrigger.compiler.UpsertTriggerSql(
                    condition='WHEN (OLD."id" IS DISTINCT FROM (NEW."id") OR OLD."created" IS DISTINCT FROM (NEW."created") OR OLD."modified" IS DISTINCT FROM (NEW."modified") OR OLD."is_comments_enabled" IS DISTINCT FROM (NEW."is_comments_enabled") OR OLD."user_id" IS DISTINCT FROM (NEW."user_id") OR OLD."profile_content_type_id" IS DISTINCT FROM (NEW."profile_content_type_id") OR OLD."profile_object_id" IS DISTINCT FROM (NEW."profile_object_id") OR OLD."body" IS DISTINCT FROM (NEW."body") OR OLD."language" IS DISTINCT FROM (NEW."language") OR OLD."is_edited" IS DISTINCT FROM (NEW."is_edited") OR OLD."is_pinned" IS DISTINCT FROM (NEW."is_pinned") OR OLD."target_content_type_id" IS DISTINCT FROM (NEW."target_content_type_id") OR OLD."target_object_id" IS DISTINCT FROM (NEW."target_object_id") OR OLD."in_reply_to_id" IS DISTINCT FROM (NEW."in_reply_to_id") OR OLD."status" IS DISTINCT FROM (NEW."status"))',
                    func='INSERT INTO "baseapp_comments_commentevent" ("body", "created", "id", "in_reply_to_id", "is_comments_enabled", "is_edited", "is_pinned", "language", "modified", "pgh_context_id", "pgh_created_at", "pgh_label", "pgh_obj_id", "pgh_operation", "profile_content_type_id", "profile_object_id", "status", "target_content_type_id", "target_object_id", "user_id") VALUES (NEW."body", NEW."created", NEW."id", NEW."in_reply_to_id", NEW."is_comments_enabled", NEW."is_edited", NEW."is_pinned", NEW."language", NEW."modified", _pgh_attach_context(), NOW(), \'snapshot\', NEW."id", 2, NEW."profile_content_type_id", NEW."profile_object_id", NEW."status", NEW."target_content_type_id", NEW."target_object_id", NEW."user_id"); RETURN NULL;',
                    hash="be0d820a5e4a9e87d7a909bae14eebad09b4e7f7",
                    operation="UPDATE",
                    pgid="pgtrigger_snapshot_update_ebf3b",
                    table="baseapp_comments_comment",
                    when="AFTER",
                ),
            ),
        ),
        pgtrigger.migrations.AddTrigger(
            model_name="comment",
            trigger=pgtrigger.compiler.Trigger(
                name="snapshot_delete",
                sql=pgtrigger.compiler.UpsertTriggerSql(
                    func='INSERT INTO "baseapp_comments_commentevent" ("body", "created", "id", "in_reply_to_id", "is_comments_enabled", "is_edited", "is_pinned", "language", "modified", "pgh_context_id", "pgh_created_at", "pgh_label", "pgh_obj_id", "pgh_operation", "profile_content_type_id", "profile_object_id", "status", "target_content_type_id", "target_object_id", "user_id") VALUES (OLD."body", OLD."created", OLD."id", OLD."in_reply_to_id", OLD."is_comments_enabled", OLD."is_edited", OLD."is_pinned", OLD."language", OLD."modified", _pgh_attach_context(), NOW(), \'snapshot\', OLD."id", 3, OLD."profile_content_type_id", OLD."profile_object_id", OLD."status", OLD."target_content_type_id", OLD."target_object_id", OLD."user_id"); RETURN NULL;',
                    hash="b7a8c64a3733fb0ebd346ad3598228755871a153",
                    operation="DELETE",
                    pgid="pgtrigger_snapshot_delete_411f5",
                    table="baseapp_comments_comment",
                    when="AFTER",
                ),
            ),
        ),
    ]
