"""
Reusable migration helpers to convert comment targets from GenericForeignKey columns
(`target_content_type`, `target_object_id`) to a `DocumentId` foreign key (`target_document`).

How to use in a project migration
---------------------------------
1. In your migration, add `target_document` fields first (for both Comment and CommentEvent
   if your history/event table mirrors the target fields).
2. Import these functions:

   from baseapp_comments.migrations.convert_comments_gfk_into_document_id_helper import (
       migrate_comment_targets_to_document_id,
       reverse_migrate_comment_targets_to_generic_fk,
   )

3. Add a `migrations.RunPython(...)` operation *before* removing old GFK columns:

   migrations.RunPython(
       migrate_comment_targets_to_document_id,
       reverse_migrate_comment_targets_to_generic_fk,
   )

4. Remove `target_content_type` and `target_object_id` fields.

Notes
-----
- The helpers resolve models using `apps.get_model(...)` so they are safe in historical
  migration state.
- Missing `DocumentId` rows are created automatically for legacy targets.
- The reverse helper restores GFK columns from `target_document`.
"""


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
