import os

import swapper
from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import models
from django.utils.translation import gettext_lazy as _
from model_utils.models import TimeStampedModel

from baseapp_comments.models import CommentableModel
from baseapp_core.graphql import RelayModel
from baseapp_core.models import random_name_in
from baseapp_reactions.models import ReactableModel
from baseapp_reports.models import ReportableModel

from .utils import default_files_count


class FileState(models.IntegerChoices):
    """File upload states for TUS protocol."""
    INITIAL = 1, _('Initial')
    RECEIVING = 2, _('Receiving')
    SAVING = 3, _('Saving')
    DONE = 4, _('Done')


class AbstractFileTarget(models.Model):
    target_content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        db_index=True,
    )
    target_object_id = models.PositiveIntegerField(db_index=True)
    target = GenericForeignKey("target_content_type", "target_object_id")

    files_count = models.JSONField(default=default_files_count)
    is_files_enabled = models.BooleanField(default=True, verbose_name=_("is files enabled"))

    class Meta:
        abstract = True
        unique_together = [("target_content_type", "target_object_id")]
        indexes = [
            models.Index(fields=["target_content_type", "target_object_id"]),
        ]

    def __str__(self):
        return f"FileTarget for {self.target_content_type} #{self.target_object_id}"


class AbstractFile(TimeStampedModel, CommentableModel, ReactableModel, ReportableModel, RelayModel):
    # TUS upload fields (using pk as identifier instead of guid)
    state = models.IntegerField(
        default=FileState.INITIAL,
        choices=FileState.choices,
    )
    upload_offset = models.BigIntegerField(default=0)
    upload_length = models.BigIntegerField(default=-1)
    upload_metadata = models.JSONField(default=dict, blank=True)
    filename = models.CharField(max_length=255, blank=True)
    expires = models.DateTimeField(null=True, blank=True)

    # File relationships
    parent_content_type = models.ForeignKey(
        ContentType,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
    )
    parent_object_id = models.PositiveIntegerField(null=True, blank=True)
    parent = GenericForeignKey("parent_content_type", "parent_object_id")

    # File metadata
    file_content_type = models.CharField(max_length=150, null=True, blank=True)
    file_name = models.CharField(max_length=512, null=True, blank=True)
    file_size = models.PositiveIntegerField(null=True, help_text=_("File size in bytes"))
    file = models.FileField(
        max_length=512, upload_to=random_name_in("files"), null=True, blank=True
    )

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

    # TUS protocol methods
    @property
    def guid(self):
        """Use pk as guid for TUS compatibility."""
        return self.pk

    def clean_fields(self, exclude=None):
        super().clean_fields(exclude=exclude)
        if self.upload_offset < 0:
            raise ValidationError(_("upload_offset should be >= 0."))

    def write_data(self, bytes_data, chunk_size):
        """
        Write chunk data efficiently using seek when supported, with fallback.

        Tries to use file.open('r+b') with seek for efficiency (works with local storage).
        Falls back to read-modify-write for storage backends that don't support seek.
        """
        if not self.file:
            # Create empty file if it doesn't exist
            self.get_or_create_temporary_file()

        # Try seek-based write first (efficient for local storage and some cloud providers)
        try:
            fh = None
            try:
                fh = self.file.open("ab")
                # TO DO: Do we need to seek?
                # fh.seek(self.upload_offset, os.SEEK_SET)
                num_bytes_written = fh.write(bytes_data)
            finally:
                if fh is not None:
                    fh.close()

            # Update offset
            if num_bytes_written > 0:
                self.upload_offset += num_bytes_written
                self.save()

        except (OSError, IOError, NotImplementedError, AttributeError):
            # Fallback: storage doesn't support r+b mode or seek (e.g., S3)
            # Use read-modify-write approach
            storage = self.file.storage
            file_name = self.file.name

            # Read existing content
            existing_content = b""
            if storage.exists(file_name):
                with storage.open(file_name, "rb") as f:
                    existing_content = f.read()

            # Append new chunk to existing content
            new_content = existing_content + bytes_data

            # Save back to storage
            storage.delete(file_name)
            storage.save(file_name, ContentFile(new_content))

            # Update offset
            num_bytes_written = len(bytes_data)
            if num_bytes_written > 0:
                self.upload_offset += num_bytes_written
                self.save()

    def generate_filename(self):
        """Generate a filename for the file."""
        return f"{self.pk or 'tmp'}.bin"

    def is_complete(self):
        """Check if upload is complete."""
        return self.upload_offset == self.upload_length

    def temporary_file_exists(self):
        """Check if file field has content."""
        return bool(self.file)

    def _temporary_file_exists(self):
        """Wrapper for temporary_file_exists."""
        return self.temporary_file_exists()

    def get_or_create_temporary_file(self):
        """
        Get or create file using Django's storage API.
        Works in distributed environments with shared storage (S3, GCS, etc.).
        """
        if not self.file:
            # Get filename from metadata or generate one
            filename = self.upload_metadata.get("filename") or self.generate_filename()

            # Create an empty file
            self.file.save(filename, ContentFile(b""), save=True)

        return self.file.name

    def start_receiving(self):
        """State transition: first chunk received."""
        if self.state == FileState.INITIAL and self._temporary_file_exists():
            self.state = FileState.RECEIVING
            self.save(update_fields=['state'])

            try:
                from rest_framework_tus import signals
                signals.receiving.send(sender=self.__class__, instance=self)
            except ImportError:
                pass

    def start_saving(self):
        """State transition: upload complete, start saving."""
        if self.state == FileState.RECEIVING and self.is_complete():
            self.state = FileState.SAVING
            self.save(update_fields=['state'])

            try:
                from rest_framework_tus import signals
                signals.saving.send(sender=self.__class__, instance=self)
            except ImportError:
                pass

    def finish(self):
        """State transition: file ready."""
        if self.state == FileState.SAVING:
            self.state = FileState.DONE
            self.save(update_fields=['state'])

            try:
                from rest_framework_tus import signals
                signals.finished.send(sender=self.__class__, instance=self)
            except ImportError:
                pass

    def save(self, *args, **kwargs):
        """
        Validate that files are enabled for the parent object before saving.
        """
        # Generate filename if not set
        if not self.filename:
            self.filename = self.generate_filename()

        # Validate files are enabled for parent
        if self.parent_content_type_id and self.parent_object_id:
            FileTarget = swapper.load_model("baseapp_files", "FileTarget")
            try:
                file_target = FileTarget.objects.get(
                    target_content_type_id=self.parent_content_type_id,
                    target_object_id=self.parent_object_id,
                )
                if not file_target.is_files_enabled:
                    raise ValidationError(
                        _("Files are not enabled for this object."),
                        code="files_disabled",
                    )
            except FileTarget.DoesNotExist:
                # If FileTarget doesn't exist, it will be created by the trigger
                # and is_files_enabled defaults to True, so we allow the save
                pass

        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        """
        Override delete to handle file deletion.
        """
        # Delete the file if it exists (works with any storage backend)
        if self.file:
            self.file.delete(save=False)

        super().delete(*args, **kwargs)

    class Meta:
        abstract = True
        # Note: Triggers are registered programmatically in the concrete app's
        # AppConfig.ready() method to properly handle swappable models.
        # See testproject.files.apps.FilesConfig.ready() for implementation.

    @classmethod
    def get_graphql_object_type(cls):
        from .graphql.object_types import FileObjectType

        return FileObjectType
