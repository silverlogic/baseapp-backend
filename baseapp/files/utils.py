from collections.abc import Iterable

import swapper
from django.contrib.contenttypes.models import ContentType
from django.db import models

from baseapp_core.models import DocumentId


def default_files_count():
    return {"total": 0}


def get_or_create_file_target(target_obj):
    """Get or create a FileTarget for the given object.

    Returns None for an unsaved/None object (the mixin guards against a NULL
    primary key rather than raising IntegrityError)."""
    FileTarget = swapper.load_model("baseapp_files", "FileTarget")
    return FileTarget.get_or_create_for_object(target_obj)


def recalculate_files_count(parent):
    if not parent:
        return

    file_target = get_or_create_file_target(parent)

    files_count_qs = parent.files.values("file_content_type").annotate(
        count=models.Count("file_content_type")
    )
    file_target.files_count = default_files_count()
    for item in files_count_qs:
        count = item["count"]
        file_target.files_count[item["file_content_type"]] = count
        file_target.files_count["total"] += count
    file_target.save(update_fields=["files_count"])


def set_files_parent(parent, files: Iterable):
    if not files:
        return

    parent_content_type = ContentType.objects.get_for_model(parent)
    parent_document_id = DocumentId.get_or_create_for_object(parent)
    previous_parents = {}

    for file_obj in files:
        previous_parent_doc_id = file_obj.parent
        if previous_parent_doc_id and previous_parent_doc_id == parent_document_id:
            continue

        if previous_parent_doc_id:
            previous_parent = previous_parent_doc_id.content_object
            key = (previous_parent_doc_id.content_type_id, previous_parent_doc_id.object_id)
            if key not in previous_parents:
                previous_parents[key] = previous_parent

        file_obj.parent = parent_document_id
        file_obj.save(update_fields=["parent"])

    for (content_type_id, object_id), previous_parent in previous_parents.items():
        if content_type_id == parent_content_type.pk and object_id == parent.pk:
            continue

        recalculate_files_count(previous_parent)
