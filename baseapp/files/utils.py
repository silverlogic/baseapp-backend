from collections.abc import Iterable
from django.contrib.contenttypes.models import ContentType
from django.db import models


def default_files_count():
    return {"total": 0}


def recalculate_files_count(parent):
    if not parent:
        return

    files_count_qs = parent.files.values("file_content_type").annotate(
        count=models.Count("file_content_type")
    )
    parent.files_count = default_files_count()
    for item in files_count_qs:
        count = item["count"]
        parent.files_count[item["file_content_type"]] = count
        parent.files_count["total"] += count
    parent.save(update_fields=["files_count"])


def set_files_parent(parent, files: Iterable):
    if not files:
        return

    parent_content_type = ContentType.objects.get_for_model(parent, for_concrete_model=False)
    previous_parents = {}

    for file_obj in files:
        previous_parent = file_obj.parent
        if (
            previous_parent
            and file_obj.parent_object_id == parent.pk
            and file_obj.parent_content_type_id == parent_content_type.pk
        ):
            continue

        if previous_parent:
            previous_parent_ct = ContentType.objects.get_for_model(
                previous_parent, for_concrete_model=False
            )
            key = (previous_parent_ct.pk, previous_parent.pk)
            if key not in previous_parents:
                previous_parents[key] = previous_parent

        file_obj.parent = parent
        file_obj.save(update_fields=["parent_content_type", "parent_object_id"])

    for (content_type_id, object_id), previous_parent in previous_parents.items():
        if content_type_id == parent_content_type.pk and object_id == parent.pk:
            continue

        recalculate_files_count(previous_parent)
