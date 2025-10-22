import swapper
from django.db import models
from django.db.models.signals import post_delete, post_save

from .models import default_files_count

File = swapper.load_model("baseapp_files", "File")


def update_files_count(sender, instance, created=False, **kwargs):
    parent = instance.parent
    if parent:
        files_count_qs = parent.files.values("content_type").annotate(
            count=models.Count("content_type")
        )
        parent.files_count = default_files_count()
        for item in files_count_qs:
            count = item["count"]
            parent.files_count[item["content_type"]] = count
            parent.files_count["total"] += count
        parent.save(update_fields=["files_count"])


post_save.connect(update_files_count, sender=File, dispatch_uid="update_files_count")
post_delete.connect(update_files_count, sender=File, dispatch_uid="update_files_count")