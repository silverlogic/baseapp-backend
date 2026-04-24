"""
Reusable migration helpers to convert comment targets from GenericForeignKey columns
(`target_content_type`, `target_object_id`) to a `DocumentId` foreign key (`target_document`).

How to use in a project migration
---------------------------------
1. In your migration, add `target_document` fields first (for both Comment and CommentEvent
   if your history/event table mirrors the target fields).
2. Import these functions:

   from baseapp_comments.migration_helpers.convert_comments_gfk_into_document_id_helper import (
       migrate_comment_targets_to_document_id,
       reverse_migrate_comment_targets_to_generic_fk,
   )

3. Add a `migrations.RunPython(...)` operation *before* removing old GFK columns:

   migrations.RunPython(
       migrate_comment_targets_to_document_id,
       reverse_migrate_comment_targets_to_generic_fk,
   )

4. Run `migrations.AlterField` to set `Comment.target_document` and
   `CommentEvent.target_document` to `null=False` **after** the backfill. The forward
   `migrate_comment_targets_to_document_id` backfills GFK, then backfills any remaining
   `CommentEvent` rows from the pghistory `pgh_obj` comment, then asserts both models.

5. Remove `target_content_type` and `target_object_id` fields.

Notes
-----
- The helpers resolve models using `apps.get_model(...)` so they are safe in historical
  migration state.
- Missing `DocumentId` rows are created automatically for legacy targets. If a comment still
  references a missing or invalid ``ContentType`` (e.g. orphaned ``target_content_type_id``),
  ``DocumentId.objects.create`` can raise ``IntegrityError`` and abort the migration; fix or
  remove bad rows in advance.
- The reverse helper restores GFK columns from `target_document`.
- After the backfill, `migrate_comment_targets_to_document_id` assert-checks both
  `Comment` and `CommentEvent` so a project migration can apply `null=False` to both
  `target_document` fields when every row is expected to be filled. Template consumers
  include `testproject` and `apps/social/comments` (see their GFK migrations for full
  schema steps).
"""


def assert_all_comment_rows_have_target_document(apps, schema_editor=None) -> None:
    """
    Fail if any ``Comment`` row has ``target_document_id`` NULL. Call after
    :func:`migrate_comment_targets_to_document_id` when the schema is about to enforce
    ``null=False`` on ``Comment.target_document``.

    The forward :func:`migrate_comment_targets_to_document_id` also invokes this at the end
    so a project migration does not need a separate ``RunPython`` for the check.
    """
    Comment = apps.get_model("comments", "Comment")
    if schema_editor is not None and getattr(schema_editor, "connection", None) is not None:
        qs = Comment.objects.using(schema_editor.connection.alias)
    else:
        qs = Comment.objects
    n = qs.filter(target_document_id__isnull=True).count()
    if n:
        raise ValueError(
            f"Comments GFK migration: {n} row(s) still have target_document_id NULL after "
            "backfill. Cannot set Comment.target_document to NOT NULL until resolved."
        )


def assert_all_commentevent_rows_have_target_document(apps, schema_editor=None) -> None:
    """
    Fail if any ``CommentEvent`` row has ``target_document_id`` NULL. Call after
    :func:`backfill_commentevent_target_from_pghistory_comment` and
    :func:`assert_all_comment_rows_have_target_document` when the schema is about to enforce
    ``null=False`` on ``CommentEvent.target_document``.

    The forward :func:`migrate_comment_targets_to_document_id` also invokes this at the end
    (after the pghistory backfill).
    """
    CommentEvent = apps.get_model("comments", "CommentEvent")
    if schema_editor is not None and getattr(schema_editor, "connection", None) is not None:
        qs = CommentEvent.objects.using(schema_editor.connection.alias)
    else:
        qs = CommentEvent.objects
    n = qs.filter(target_document_id__isnull=True).count()
    if n:
        raise ValueError(
            f"Comments GFK migration: {n} commentevent row(s) still have target_document_id "
            "NULL after backfill. Cannot set CommentEvent.target_document to NOT NULL until "
            "resolved."
        )


def backfill_commentevent_target_from_pghistory_comment(apps, schema_editor=None) -> None:
    """
    For history rows that still have NULL ``target_document_id`` but have a pghistory
    ``pgh_obj`` to a ``Comment``, copy ``comment.target_document_id`` onto the event. Runs
    after the GFK-based backfill for cases where the event had no resolvable
    (``target_content_type_id``, ``target_object_id``) but the parent comment is filled.
    """
    Comment = apps.get_model("comments", "Comment")
    CommentEvent = apps.get_model("comments", "CommentEvent")
    if schema_editor is not None and getattr(schema_editor, "connection", None) is not None:
        alias = schema_editor.connection.alias
        e_qs = CommentEvent.objects.using(alias)
        c_qs = Comment.objects.using(alias)
    else:
        e_qs = CommentEvent.objects
        c_qs = Comment.objects

    for event in (
        e_qs.filter(target_document_id__isnull=True).exclude(pgh_obj_id__isnull=True).iterator()
    ):
        comment = c_qs.filter(pk=event.pgh_obj_id).first()
        if comment is None:
            continue
        tid = comment.target_document_id
        if tid:
            e_qs.filter(pk=event.pk).update(target_document_id=tid)


def migrate_comment_targets_to_document_id(apps, schema_editor):
    Comment = apps.get_model("comments", "Comment")
    CommentEvent = apps.get_model("comments", "CommentEvent")
    DocumentId = apps.get_model("baseapp_core", "DocumentId")

    doc_map = {
        (doc["content_type_id"], doc["object_id"]): doc["id"]
        for doc in DocumentId.objects.values("id", "content_type_id", "object_id")
    }

    target_pairs = (
        Comment.objects.exclude(target_content_type_id__isnull=True)
        .exclude(target_object_id__isnull=True)
        .values_list("target_content_type_id", "target_object_id")
        .distinct()
    )
    for content_type_id, object_id in target_pairs:
        key = (content_type_id, object_id)
        if key not in doc_map:
            # Unhandled: bad FK to django_content_type raises IntegrityError and stops migrate.
            doc = DocumentId.objects.create(content_type_id=content_type_id, object_id=object_id)
            doc_map[key] = doc.id

    for comment in Comment.objects.filter(target_document_id__isnull=True).exclude(
        target_content_type_id__isnull=True
    ):
        key = (comment.target_content_type_id, comment.target_object_id)
        document_id = doc_map.get(key)
        if document_id:
            Comment.objects.filter(pk=comment.pk).update(target_document_id=document_id)

    for event in CommentEvent.objects.filter(target_document_id__isnull=True).exclude(
        target_content_type_id__isnull=True
    ):
        key = (event.target_content_type_id, event.target_object_id)
        document_id = doc_map.get(key)
        if document_id:
            CommentEvent.objects.filter(pk=event.pk).update(target_document_id=document_id)

    backfill_commentevent_target_from_pghistory_comment(apps, schema_editor=schema_editor)
    assert_all_comment_rows_have_target_document(apps, schema_editor=schema_editor)
    assert_all_commentevent_rows_have_target_document(apps, schema_editor=schema_editor)


def reverse_migrate_comment_targets_to_generic_fk(apps, schema_editor):
    Comment = apps.get_model("comments", "Comment")
    CommentEvent = apps.get_model("comments", "CommentEvent")

    for comment in Comment.objects.filter(target_document_id__isnull=False).select_related(
        "target_document"
    ):
        Comment.objects.filter(pk=comment.pk).update(
            target_content_type_id=comment.target_document.content_type_id,
            target_object_id=comment.target_document.object_id,
        )

    for event in CommentEvent.objects.filter(target_document_id__isnull=False).select_related(
        "target_document"
    ):
        CommentEvent.objects.filter(pk=event.pk).update(
            target_content_type_id=event.target_document.content_type_id,
            target_object_id=event.target_document.object_id,
        )
