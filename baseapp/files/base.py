import swapper
from django.contrib.contenttypes.models import ContentType
from django.db import models

from baseapp_core.models import DocumentId

from .utils import get_or_create_file_target


class FileableModel(models.Model):
    class Meta:
        abstract = True

    @property
    def files(self):
        """Returns files related to this object through DocumentId."""
        File = swapper.load_model("baseapp_files", "File")
        content_type = ContentType.objects.get_for_model(self, for_concrete_model=False)
        try:
            document_id = DocumentId.objects.get(
                content_type=content_type,
                object_id=self.pk,
            )
            return File.objects.filter(parent=document_id)
        except DocumentId.DoesNotExist:
            return File.objects.none()

    def get_file_target(self):
        return get_or_create_file_target(self)

    @property
    def files_count(self):
        return self.get_file_target().files_count

    @property
    def is_files_enabled(self):
        return self.get_file_target().is_files_enabled
