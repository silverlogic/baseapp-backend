import swapper
from django.contrib.contenttypes.models import ContentType
from django.db import models

from .utils import get_or_create_file_target


class FileableModel(models.Model):
    class Meta:
        abstract = True

    @property
    def files(self) -> models.QuerySet:
        """Returns files related to this object through the DocumentId join."""
        File = swapper.load_model("baseapp_files", "File")
        content_type = ContentType.objects.get_for_model(self)
        return File.objects.filter(
            parent__content_type=content_type,
            parent__object_id=self.pk,
        )

    def get_file_target(self):
        return get_or_create_file_target(self)

    @property
    def files_count(self) -> dict:
        return self.get_file_target().files_count

    @property
    def is_files_enabled(self) -> bool:
        return self.get_file_target().is_files_enabled
