import pghistory
from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey, GenericRelation
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils.translation import gettext_lazy as _
from model_utils.models import TimeStampedModel
from base.utils.upload import set_upload_to_random_filename


def default_files_count():
    return {"total": 0}


class FilesModel(models.Model):
    files_count = models.JSONField(default=default_files_count)
    files = GenericRelation(
        "baseapp_files.File",
        content_type_field="parent_content_type",
        object_id_field="parent_object_id",
    )

    class Meta:
        abstract = True


@pghistory.track(pghistory.Snapshot())
class File(TimeStampedModel):
    parent_content_type = models.ForeignKey(
        ContentType,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
    )
    parent_object_id = models.PositiveIntegerField(null=True, blank=True)
    parent = GenericForeignKey("parent_content_type", "parent_object_id")

    content_type = models.CharField(max_length=150, null=True, blank=True)
    file_name = models.CharField(max_length=512, null=True, blank=True)
    file_size = models.PositiveIntegerField(null=True, help_text=_("File size in bytes"))
    file = models.FileField(
        max_length=512, upload_to=set_upload_to_random_filename("files")
    )

    name = models.CharField(max_length=512, null=True, blank=True)
    description = models.TextField(null=True, blank=True)

    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="files_created",
        on_delete=models.CASCADE,
        null=True,
    )

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)

        parent = self.parent
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
