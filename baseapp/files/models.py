import swapper
from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils.translation import gettext_lazy as _
from model_utils.models import TimeStampedModel

from baseapp_comments.models import CommentableModel
from baseapp_core.graphql import RelayModel
from baseapp_core.models import random_name_in
from baseapp_reactions.models import ReactableModel
from baseapp_reports.models import ReportableModel


class AbstractFile(TimeStampedModel, CommentableModel, ReactableModel, ReportableModel, RelayModel):
    parent_content_type = models.ForeignKey(
        ContentType,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
    )
    parent_object_id = models.PositiveIntegerField(null=True, blank=True)
    parent = GenericForeignKey("parent_content_type", "parent_object_id")

    file_content_type = models.CharField(max_length=150, null=True, blank=True)
    file_name = models.CharField(max_length=512, null=True, blank=True)
    file_size = models.PositiveIntegerField(null=True, help_text=_("File size in bytes"))
    file = models.FileField(max_length=512, upload_to=random_name_in("files"))

    name = models.CharField(max_length=512, null=True, blank=True)
    description = models.TextField(null=True, blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="files_created",
        on_delete=models.CASCADE,
        null=True,
    )
    profile = models.ForeignKey(
        swapper.get_model_name("baseapp_profiles", "Profile"),
        verbose_name=_("profile"),
        related_name="files",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    class Meta:
        abstract = True

    @classmethod
    def get_graphql_object_type(cls):
        from .graphql.object_types import FileObjectType

        return FileObjectType


class File(AbstractFile):
    class Meta(AbstractFile.Meta):
        abstract = False
        swappable = swapper.swappable_setting("baseapp_files", "File")
