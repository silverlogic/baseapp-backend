import swapper
from django.contrib.contenttypes.fields import GenericRelation
from django.db import models


class FileableModel(models.Model):
    files = GenericRelation(
        swapper.get_model_name("baseapp_files", "File"),
        content_type_field="parent_content_type",
        object_id_field="parent_object_id",
    )

    class Meta:
        abstract = True

    def get_file_target(self):
        from .utils import get_or_create_file_target

        return get_or_create_file_target(self)

    @property
    def files_count(self):
        return self.get_file_target().files_count

    @property
    def is_files_enabled(self):
        return self.get_file_target().is_files_enabled
