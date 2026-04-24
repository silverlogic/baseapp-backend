# After CommentableMetadata exists, copy legacy mixin fields from Comment, then remove columns and
# refresh pghistory triggers (GFK-based). target_document pghistory triggers are added in 0004.

import pgtrigger.compiler
import pgtrigger.migrations
from django.db import migrations

from baseapp_comments.migration_helpers.convert_legacy_commentable_fields_into_metadata_helper import (
    migrate_legacy_commentable_fields_to_metadata,
    reverse_migrate_legacy_commentable_fields_from_metadata,
)


def migrate_comment_commentable_to_metadata(apps, schema_editor):
    migrate_legacy_commentable_fields_to_metadata(
        apps,
        schema_editor,
        source_app_label="comments",
        source_model_name="Comment",
    )


def reverse_migrate_comment_commentable_from_metadata(apps, schema_editor):
    reverse_migrate_legacy_commentable_fields_from_metadata(
        apps,
        schema_editor,
        source_app_label="comments",
        source_model_name="Comment",
    )


class Migration(migrations.Migration):
    dependencies = [
        ("comments", "0002_commentablemetadata"),
    ]

    operations = [
        migrations.RunPython(
            migrate_comment_commentable_to_metadata,
            reverse_migrate_comment_commentable_from_metadata,
        ),
        pgtrigger.migrations.RemoveTrigger(
            model_name="comment",
            name="insert_insert",
        ),
        pgtrigger.migrations.RemoveTrigger(
            model_name="comment",
            name="update_update",
        ),
        pgtrigger.migrations.RemoveTrigger(
            model_name="comment",
            name="delete_delete",
        ),
        migrations.RemoveField(
            model_name="comment",
            name="comments_count",
        ),
        migrations.RemoveField(
            model_name="comment",
            name="is_comments_enabled",
        ),
        migrations.RemoveField(
            model_name="commentevent",
            name="is_comments_enabled",
        ),
        pgtrigger.migrations.AddTrigger(
            model_name="comment",
            trigger=pgtrigger.compiler.Trigger(
                name="insert_insert",
                sql=pgtrigger.compiler.UpsertTriggerSql(
                    func='INSERT INTO "comments_commentevent" ("body", "created", "id", "in_reply_to_id", "is_edited", "is_pinned", "is_reactions_enabled", "language", "pgh_context_id", "pgh_created_at", "pgh_label", "pgh_obj_id", "profile_id", "reports_count", "status", "target_content_type_id", "target_object_id", "user_id") VALUES (NEW."body", NEW."created", NEW."id", NEW."in_reply_to_id", NEW."is_edited", NEW."is_pinned", NEW."is_reactions_enabled", NEW."language", _pgh_attach_context(), NOW(), \'insert\', NEW."id", NEW."profile_id", NEW."reports_count", NEW."status", NEW."target_content_type_id", NEW."target_object_id", NEW."user_id"); RETURN NULL;',
                    hash="67dba742c66fb15c3830c2f36a2b316009903b3e",
                    operation="INSERT",
                    pgid="pgtrigger_insert_insert_18fd9",
                    table="comments_comment",
                    when="AFTER",
                ),
            ),
        ),
        pgtrigger.migrations.AddTrigger(
            model_name="comment",
            trigger=pgtrigger.compiler.Trigger(
                name="update_update",
                sql=pgtrigger.compiler.UpsertTriggerSql(
                    condition='WHEN (OLD."body" IS DISTINCT FROM (NEW."body") OR OLD."created" IS DISTINCT FROM (NEW."created") OR OLD."id" IS DISTINCT FROM (NEW."id") OR OLD."in_reply_to_id" IS DISTINCT FROM (NEW."in_reply_to_id") OR OLD."is_edited" IS DISTINCT FROM (NEW."is_edited") OR OLD."is_pinned" IS DISTINCT FROM (NEW."is_pinned") OR OLD."is_reactions_enabled" IS DISTINCT FROM (NEW."is_reactions_enabled") OR OLD."language" IS DISTINCT FROM (NEW."language") OR OLD."profile_id" IS DISTINCT FROM (NEW."profile_id") OR OLD."reports_count" IS DISTINCT FROM (NEW."reports_count") OR OLD."status" IS DISTINCT FROM (NEW."status") OR OLD."target_content_type_id" IS DISTINCT FROM (NEW."target_content_type_id") OR OLD."target_object_id" IS DISTINCT FROM (NEW."target_object_id") OR OLD."user_id" IS DISTINCT FROM (NEW."user_id"))',
                    func='INSERT INTO "comments_commentevent" ("body", "created", "id", "in_reply_to_id", "is_edited", "is_pinned", "is_reactions_enabled", "language", "pgh_context_id", "pgh_created_at", "pgh_label", "pgh_obj_id", "profile_id", "reports_count", "status", "target_content_type_id", "target_object_id", "user_id") VALUES (NEW."body", NEW."created", NEW."id", NEW."in_reply_to_id", NEW."is_edited", NEW."is_pinned", NEW."is_reactions_enabled", NEW."language", _pgh_attach_context(), NOW(), \'update\', NEW."id", NEW."profile_id", NEW."reports_count", NEW."status", NEW."target_content_type_id", NEW."target_object_id", NEW."user_id"); RETURN NULL;',
                    hash="ead734b59c220efdd0a54901be04af7d64436419",
                    operation="UPDATE",
                    pgid="pgtrigger_update_update_230ec",
                    table="comments_comment",
                    when="AFTER",
                ),
            ),
        ),
        pgtrigger.migrations.AddTrigger(
            model_name="comment",
            trigger=pgtrigger.compiler.Trigger(
                name="delete_delete",
                sql=pgtrigger.compiler.UpsertTriggerSql(
                    func='INSERT INTO "comments_commentevent" ("body", "created", "id", "in_reply_to_id", "is_edited", "is_pinned", "is_reactions_enabled", "language", "pgh_context_id", "pgh_created_at", "pgh_label", "pgh_obj_id", "profile_id", "reports_count", "status", "target_content_type_id", "target_object_id", "user_id") VALUES (OLD."body", OLD."created", OLD."id", OLD."in_reply_to_id", OLD."is_edited", OLD."is_pinned", OLD."is_reactions_enabled", OLD."language", _pgh_attach_context(), NOW(), \'delete\', OLD."id", OLD."profile_id", OLD."reports_count", OLD."status", OLD."target_content_type_id", OLD."target_object_id", OLD."user_id"); RETURN NULL;',
                    hash="871e9fa6745bcc3fe3ba7ad9c6203f33ebb7161a",
                    operation="DELETE",
                    pgid="pgtrigger_delete_delete_ff62f",
                    table="comments_comment",
                    when="AFTER",
                ),
            ),
        ),
    ]
