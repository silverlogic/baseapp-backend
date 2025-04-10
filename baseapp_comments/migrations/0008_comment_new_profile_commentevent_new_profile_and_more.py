import django.db.models.deletion
import pgtrigger.compiler
import pgtrigger.migrations
import swapper
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        swapper.dependency("baseapp_profiles", "Profile"),
        ("baseapp_comments", "0007_remove_comment_insert_insert_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="comment",
            name="new_profile",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="comments",
                to=swapper.get_model_name("baseapp_profiles", "Profile"),
                verbose_name="profile",
            ),
        ),
        migrations.AddField(
            model_name="commentevent",
            name="new_profile",
            field=models.ForeignKey(
                blank=True,
                db_constraint=False,
                null=True,
                on_delete=django.db.models.deletion.DO_NOTHING,
                related_name="+",
                related_query_name="+",
                to=swapper.get_model_name("baseapp_profiles", "Profile"),
                verbose_name="profile",
            ),
        ),
        pgtrigger.migrations.AddTrigger(
            model_name="comment",
            trigger=pgtrigger.compiler.Trigger(
                name="insert_insert",
                sql=pgtrigger.compiler.UpsertTriggerSql(
                    func='INSERT INTO "baseapp_comments_commentevent" ("body", "created", "id", "in_reply_to_id", "is_comments_enabled", "is_edited", "is_pinned", "is_reactions_enabled", "language", "modified", "new_profile_id", "pgh_context_id", "pgh_created_at", "pgh_label", "pgh_obj_id", "profile_content_type_id", "profile_object_id", "reports_count", "status", "target_content_type_id", "target_object_id", "user_id") VALUES (NEW."body", NEW."created", NEW."id", NEW."in_reply_to_id", NEW."is_comments_enabled", NEW."is_edited", NEW."is_pinned", NEW."is_reactions_enabled", NEW."language", NEW."modified", NEW."new_profile_id", _pgh_attach_context(), NOW(), \'insert\', NEW."id", NEW."profile_content_type_id", NEW."profile_object_id", NEW."reports_count", NEW."status", NEW."target_content_type_id", NEW."target_object_id", NEW."user_id"); RETURN NULL;',
                    hash="ae12e560316e8e6817ce58641720395d5da99ad6",
                    operation="INSERT",
                    pgid="pgtrigger_insert_insert_167ad",
                    table="baseapp_comments_comment",
                    when="AFTER",
                ),
            ),
        ),
        pgtrigger.migrations.AddTrigger(
            model_name="comment",
            trigger=pgtrigger.compiler.Trigger(
                name="update_update",
                sql=pgtrigger.compiler.UpsertTriggerSql(
                    condition='WHEN (OLD."body" IS DISTINCT FROM (NEW."body") OR OLD."created" IS DISTINCT FROM (NEW."created") OR OLD."id" IS DISTINCT FROM (NEW."id") OR OLD."in_reply_to_id" IS DISTINCT FROM (NEW."in_reply_to_id") OR OLD."is_comments_enabled" IS DISTINCT FROM (NEW."is_comments_enabled") OR OLD."is_edited" IS DISTINCT FROM (NEW."is_edited") OR OLD."is_pinned" IS DISTINCT FROM (NEW."is_pinned") OR OLD."is_reactions_enabled" IS DISTINCT FROM (NEW."is_reactions_enabled") OR OLD."language" IS DISTINCT FROM (NEW."language") OR OLD."modified" IS DISTINCT FROM (NEW."modified") OR OLD."new_profile_id" IS DISTINCT FROM (NEW."new_profile_id") OR OLD."profile_content_type_id" IS DISTINCT FROM (NEW."profile_content_type_id") OR OLD."profile_object_id" IS DISTINCT FROM (NEW."profile_object_id") OR OLD."reports_count" IS DISTINCT FROM (NEW."reports_count") OR OLD."status" IS DISTINCT FROM (NEW."status") OR OLD."target_content_type_id" IS DISTINCT FROM (NEW."target_content_type_id") OR OLD."target_object_id" IS DISTINCT FROM (NEW."target_object_id") OR OLD."user_id" IS DISTINCT FROM (NEW."user_id"))',
                    func='INSERT INTO "baseapp_comments_commentevent" ("body", "created", "id", "in_reply_to_id", "is_comments_enabled", "is_edited", "is_pinned", "is_reactions_enabled", "language", "modified", "new_profile_id", "pgh_context_id", "pgh_created_at", "pgh_label", "pgh_obj_id", "profile_content_type_id", "profile_object_id", "reports_count", "status", "target_content_type_id", "target_object_id", "user_id") VALUES (NEW."body", NEW."created", NEW."id", NEW."in_reply_to_id", NEW."is_comments_enabled", NEW."is_edited", NEW."is_pinned", NEW."is_reactions_enabled", NEW."language", NEW."modified", NEW."new_profile_id", _pgh_attach_context(), NOW(), \'update\', NEW."id", NEW."profile_content_type_id", NEW."profile_object_id", NEW."reports_count", NEW."status", NEW."target_content_type_id", NEW."target_object_id", NEW."user_id"); RETURN NULL;',
                    hash="ea14a07c4e521ca1988279c4cf59c1266f628a42",
                    operation="UPDATE",
                    pgid="pgtrigger_update_update_c3a2a",
                    table="baseapp_comments_comment",
                    when="AFTER",
                ),
            ),
        ),
        pgtrigger.migrations.AddTrigger(
            model_name="comment",
            trigger=pgtrigger.compiler.Trigger(
                name="delete_delete",
                sql=pgtrigger.compiler.UpsertTriggerSql(
                    func='INSERT INTO "baseapp_comments_commentevent" ("body", "created", "id", "in_reply_to_id", "is_comments_enabled", "is_edited", "is_pinned", "is_reactions_enabled", "language", "modified", "new_profile_id", "pgh_context_id", "pgh_created_at", "pgh_label", "pgh_obj_id", "profile_content_type_id", "profile_object_id", "reports_count", "status", "target_content_type_id", "target_object_id", "user_id") VALUES (OLD."body", OLD."created", OLD."id", OLD."in_reply_to_id", OLD."is_comments_enabled", OLD."is_edited", OLD."is_pinned", OLD."is_reactions_enabled", OLD."language", OLD."modified", OLD."new_profile_id", _pgh_attach_context(), NOW(), \'delete\', OLD."id", OLD."profile_content_type_id", OLD."profile_object_id", OLD."reports_count", OLD."status", OLD."target_content_type_id", OLD."target_object_id", OLD."user_id"); RETURN NULL;',
                    hash="5910e6aa24b27c37ce133f037644ae10c9cf44fc",
                    operation="DELETE",
                    pgid="pgtrigger_delete_delete_50362",
                    table="baseapp_comments_comment",
                    when="AFTER",
                ),
            ),
        ),
    ]
