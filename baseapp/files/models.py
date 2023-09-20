import pgtrigger
import swapper
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.signals import class_prepared
from django.dispatch import receiver
from django.utils.translation import gettext_lazy as _
from model_utils.models import TimeStampedModel

from baseapp_comments.models import CommentableModel
from baseapp_core.graphql import RelayModel
from baseapp_core.models import DocumentId, random_name_in
from baseapp_reactions.models import ReactableModel
from baseapp_reports.models import ReportableModel

from .utils import default_files_count


class FileTargetCountFunc(pgtrigger.Func):
    """
    Reusable pgtrigger function for updating FileTarget counts.
    Dynamically resolves table names for swappable models.
    """

    def render(
        self,
        meta=None,
        fields=None,
        columns=None,
        **kwargs,
    ) -> str:
        FileTarget = swapper.load_model("baseapp_files", "FileTarget")
        return self.func.format(
            file_table=meta.db_table,
            file_target_table=FileTarget._meta.db_table,
        )


def file_target_insert_trigger():
    """Trigger to update FileTarget counts when a file is inserted."""
    return pgtrigger.Trigger(
        name="update_file_target_on_insert",
        level=pgtrigger.Row,
        when=pgtrigger.After,
        operation=pgtrigger.Insert,
        func=FileTargetCountFunc(
            """
            DECLARE
                new_counts JSONB;
            BEGIN
                IF NEW.parent_id IS NOT NULL THEN
                    -- Calculate new counts
                    SELECT COALESCE(
                        jsonb_object_agg(
                            file_content_type,
                            count
                        ) || jsonb_build_object('total', SUM(count)),
                        '{{"total": 0}}'::jsonb
                    ) INTO new_counts
                    FROM (
                        SELECT
                            COALESCE(file_content_type, 'unknown') as file_content_type,
                            COUNT(*)::int as count
                        FROM {file_table}
                        WHERE parent_id = NEW.parent_id
                        GROUP BY file_content_type
                    ) counts;

                    -- Insert or update FileTarget
                    INSERT INTO {file_target_table} (target_id, files_count, is_files_enabled)
                    VALUES (NEW.parent_id, new_counts, true)
                    ON CONFLICT (target_id)
                    DO UPDATE SET files_count = new_counts;
                END IF;
                RETURN NEW;
            END;
            """
        ),
    )


def file_target_update_trigger():
    """Trigger to update FileTarget counts when a file's parent is updated."""
    return pgtrigger.Trigger(
        name="update_file_target_on_update",
        level=pgtrigger.Row,
        when=pgtrigger.After,
        operation=pgtrigger.Update,
        func=FileTargetCountFunc(
            """
            DECLARE
                new_counts JSONB;
                old_counts JSONB;
            BEGIN
                -- Update old parent if it changed
                IF OLD.parent_id IS DISTINCT FROM NEW.parent_id
                    AND OLD.parent_id IS NOT NULL THEN

                    SELECT COALESCE(
                        jsonb_object_agg(
                            file_content_type,
                            count
                        ) || jsonb_build_object('total', SUM(count)),
                        '{{"total": 0}}'::jsonb
                    ) INTO old_counts
                    FROM (
                        SELECT
                            COALESCE(file_content_type, 'unknown') as file_content_type,
                            COUNT(*)::int as count
                        FROM {file_table}
                        WHERE parent_id = OLD.parent_id
                        GROUP BY file_content_type
                    ) counts;

                    UPDATE {file_target_table} SET files_count = old_counts
                    WHERE target_id = OLD.parent_id;
                END IF;

                -- Update new parent
                IF NEW.parent_id IS NOT NULL THEN
                    SELECT COALESCE(
                        jsonb_object_agg(
                            file_content_type,
                            count
                        ) || jsonb_build_object('total', SUM(count)),
                        '{{"total": 0}}'::jsonb
                    ) INTO new_counts
                    FROM (
                        SELECT
                            COALESCE(file_content_type, 'unknown') as file_content_type,
                            COUNT(*)::int as count
                        FROM {file_table}
                        WHERE parent_id = NEW.parent_id
                        GROUP BY file_content_type
                    ) counts;

                    INSERT INTO {file_target_table} (target_id, files_count, is_files_enabled)
                    VALUES (NEW.parent_id, new_counts, true)
                    ON CONFLICT (target_id)
                    DO UPDATE SET files_count = new_counts;
                END IF;

                RETURN NEW;
            END;
            """
        ),
    )


def file_target_delete_trigger():
    """Trigger to update FileTarget counts when a file is deleted."""
    return pgtrigger.Trigger(
        name="update_file_target_on_delete",
        level=pgtrigger.Row,
        when=pgtrigger.After,
        operation=pgtrigger.Delete,
        func=FileTargetCountFunc(
            """
            DECLARE
                new_counts JSONB;
            BEGIN
                IF OLD.parent_id IS NOT NULL THEN
                    SELECT COALESCE(
                        jsonb_object_agg(
                            file_content_type,
                            count
                        ) || jsonb_build_object('total', SUM(count)),
                        '{{"total": 0}}'::jsonb
                    ) INTO new_counts
                    FROM (
                        SELECT
                            COALESCE(file_content_type, 'unknown') as file_content_type,
                            COUNT(*)::int as count
                        FROM {file_table}
                        WHERE parent_id = OLD.parent_id
                        GROUP BY file_content_type
                    ) counts;

                    UPDATE {file_target_table} SET files_count = new_counts
                    WHERE target_id = OLD.parent_id;
                END IF;

                RETURN OLD;
            END;
            """
        ),
    )


@receiver(class_prepared)
def add_file_target_triggers(sender, **kwargs):
    """
    Add the FileTarget count triggers to the model when it is prepared.
    This handles swappable models by adding triggers to the concrete model.
    """
    # Only models that inherit from AbstractFile
    if not issubclass(sender, AbstractFile):
        return

    # Skip non-schema models
    if sender._meta.abstract or sender._meta.proxy:
        return

    # Skip swapped-out models
    if sender._meta.swapped:
        return

    if not hasattr(sender._meta, "triggers"):
        sender._meta.triggers = []

    existing = [t.name for t in sender._meta.triggers]
    if "update_file_target_on_insert" not in existing:
        sender._meta.triggers.append(file_target_insert_trigger())
    if "update_file_target_on_update" not in existing:
        sender._meta.triggers.append(file_target_update_trigger())
    if "update_file_target_on_delete" not in existing:
        sender._meta.triggers.append(file_target_delete_trigger())


class AbstractFileTarget(models.Model):
    target = models.OneToOneField(
        DocumentId,
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="file_target",
        help_text=_("The document this file target belongs to"),
    )

    files_count = models.JSONField(default=default_files_count)
    is_files_enabled = models.BooleanField(default=True, verbose_name=_("is files enabled"))

    class Meta:
        abstract = True

    def __str__(self):
        return f"FileTarget for {self.target}"


class AbstractFile(TimeStampedModel, CommentableModel, ReactableModel, ReportableModel, RelayModel):
    parent = models.ForeignKey(
        DocumentId,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="files",
        help_text=_("The parent document this file belongs to"),
    )

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

    # Upload status tracking
    class UploadStatus(models.TextChoices):
        PENDING = "pending", _("Pending Upload")
        UPLOADING = "uploading", _("Upload in Progress")
        COMPLETED = "completed", _("Upload Completed")
        FAILED = "failed", _("Upload Failed")
        ABORTED = "aborted", _("Upload Aborted")

    upload_status = models.CharField(
        max_length=20,
        choices=UploadStatus.choices,
        default=UploadStatus.COMPLETED,
        db_index=True,
        help_text=_("Status of the file upload"),
    )

    # S3 multipart upload tracking
    upload_id = models.CharField(
        max_length=512,
        null=True,
        blank=True,
        help_text=_("S3 multipart upload ID for in-progress uploads"),
    )

    # Metadata for multipart uploads
    total_parts = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text=_("Total number of parts for multipart upload"),
    )

    uploaded_parts = models.JSONField(
        null=True,
        blank=True,
        default=dict,
        help_text=_("Tracking uploaded parts with ETags"),
    )

    # Upload expiration for cleanup
    upload_expires_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        help_text=_("Expiration time for pending uploads"),
    )

    def save(self, *args, **kwargs):
        """
        Validate that files are enabled for the parent object before saving.
        """
        if self.parent_id:
            FileTarget = swapper.load_model("baseapp_files", "FileTarget")
            try:
                file_target = FileTarget.objects.get(target_id=self.parent_id)
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

    class Meta:
        abstract = True
        # Note: Triggers are registered via the class_prepared signal in this module
        # to properly handle swappable models.

    @classmethod
    def get_graphql_object_type(cls):
        from .graphql.object_types import FileObjectType

        return FileObjectType
