import swapper
from django.contrib.contenttypes.fields import GenericRelation
from django.db import models
from django.utils.translation import gettext_lazy as _

from .utils import default_files_count


class FileableModel(models.Model):
    files_count = models.JSONField(default=default_files_count)
    files = GenericRelation(
        swapper.get_model_name("baseapp_files", "File"),
        content_type_field="parent_content_type",
        object_id_field="parent_object_id",
    )
    is_files_enabled = models.BooleanField(default=True, verbose_name=_("is files enabled"))

    class Meta:
        abstract = True
