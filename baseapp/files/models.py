import pgtrigger
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

from .utils import default_files_count


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
        triggers = [
            pgtrigger.Trigger(
                name="update_file_target_on_insert",
                operation=pgtrigger.Insert,
                when=pgtrigger.After,
                func="""
                    -- Get the swappable FileTarget table name
                    DECLARE
                        file_target_table TEXT;
                        new_counts JSONB;
                    BEGIN
                        -- Get FileTarget table name from app registry
                        SELECT pg_class.relname INTO file_target_table
                        FROM pg_class
                        JOIN pg_namespace ON pg_namespace.oid = pg_class.relnamespace
                        WHERE pg_namespace.nspname = 'public'
                        AND pg_class.relname LIKE '%filetarget';

                        IF NEW.parent_content_type_id IS NOT NULL AND NEW.parent_object_id IS NOT NULL THEN
                            -- Calculate new counts
                            SELECT COALESCE(
                                jsonb_object_agg(
                                    file_content_type,
                                    count
                                ) || jsonb_build_object('total', SUM(count)),
                                '{"total": 0}'::jsonb
                            ) INTO new_counts
                            FROM (
                                SELECT
                                    COALESCE(file_content_type, 'unknown') as file_content_type,
                                    COUNT(*)::int as count
                                FROM files_file
                                WHERE parent_content_type_id = NEW.parent_content_type_id
                                AND parent_object_id = NEW.parent_object_id
                                GROUP BY file_content_type
                            ) counts;

                            -- Insert or update FileTarget
                            EXECUTE format(
                                'INSERT INTO %I (target_content_type_id, target_object_id, files_count, is_files_enabled)
                                VALUES ($1, $2, $3, true)
                                ON CONFLICT (target_content_type_id, target_object_id)
                                DO UPDATE SET files_count = $3',
                                file_target_table
                            ) USING NEW.parent_content_type_id, NEW.parent_object_id, new_counts;
                        END IF;
                        RETURN NEW;
                    END;
                """,
            ),
            pgtrigger.Trigger(
                name="update_file_target_on_update",
                operation=pgtrigger.Update,
                when=pgtrigger.After,
                func="""
                    DECLARE
                        file_target_table TEXT;
                        new_counts JSONB;
                        old_counts JSONB;
                    BEGIN
                        SELECT pg_class.relname INTO file_target_table
                        FROM pg_class
                        JOIN pg_namespace ON pg_namespace.oid = pg_class.relnamespace
                        WHERE pg_namespace.nspname = 'public'
                        AND pg_class.relname LIKE '%filetarget';

                        -- Update old parent if it changed
                        IF (OLD.parent_content_type_id IS DISTINCT FROM NEW.parent_content_type_id
                            OR OLD.parent_object_id IS DISTINCT FROM NEW.parent_object_id)
                            AND OLD.parent_content_type_id IS NOT NULL
                            AND OLD.parent_object_id IS NOT NULL THEN

                            SELECT COALESCE(
                                jsonb_object_agg(
                                    file_content_type,
                                    count
                                ) || jsonb_build_object('total', SUM(count)),
                                '{"total": 0}'::jsonb
                            ) INTO old_counts
                            FROM (
                                SELECT
                                    COALESCE(file_content_type, 'unknown') as file_content_type,
                                    COUNT(*)::int as count
                                FROM files_file
                                WHERE parent_content_type_id = OLD.parent_content_type_id
                                AND parent_object_id = OLD.parent_object_id
                                GROUP BY file_content_type
                            ) counts;

                            EXECUTE format(
                                'UPDATE %I SET files_count = $1
                                WHERE target_content_type_id = $2 AND target_object_id = $3',
                                file_target_table
                            ) USING old_counts, OLD.parent_content_type_id, OLD.parent_object_id;
                        END IF;

                        -- Update new parent
                        IF NEW.parent_content_type_id IS NOT NULL AND NEW.parent_object_id IS NOT NULL THEN
                            SELECT COALESCE(
                                jsonb_object_agg(
                                    file_content_type,
                                    count
                                ) || jsonb_build_object('total', SUM(count)),
                                '{"total": 0}'::jsonb
                            ) INTO new_counts
                            FROM (
                                SELECT
                                    COALESCE(file_content_type, 'unknown') as file_content_type,
                                    COUNT(*)::int as count
                                FROM files_file
                                WHERE parent_content_type_id = NEW.parent_content_type_id
                                AND parent_object_id = NEW.parent_object_id
                                GROUP BY file_content_type
                            ) counts;

                            EXECUTE format(
                                'INSERT INTO %I (target_content_type_id, target_object_id, files_count, is_files_enabled)
                                VALUES ($1, $2, $3, true)
                                ON CONFLICT (target_content_type_id, target_object_id)
                                DO UPDATE SET files_count = $3',
                                file_target_table
                            ) USING NEW.parent_content_type_id, NEW.parent_object_id, new_counts;
                        END IF;

                        RETURN NEW;
                    END;
                """,
            ),
            pgtrigger.Trigger(
                name="update_file_target_on_delete",
                operation=pgtrigger.Delete,
                when=pgtrigger.After,
                func="""
                    DECLARE
                        file_target_table TEXT;
                        new_counts JSONB;
                    BEGIN
                        SELECT pg_class.relname INTO file_target_table
                        FROM pg_class
                        JOIN pg_namespace ON pg_namespace.oid = pg_class.relnamespace
                        WHERE pg_namespace.nspname = 'public'
                        AND pg_class.relname LIKE '%filetarget';

                        IF OLD.parent_content_type_id IS NOT NULL AND OLD.parent_object_id IS NOT NULL THEN
                            SELECT COALESCE(
                                jsonb_object_agg(
                                    file_content_type,
                                    count
                                ) || jsonb_build_object('total', SUM(count)),
                                '{"total": 0}'::jsonb
                            ) INTO new_counts
                            FROM (
                                SELECT
                                    COALESCE(file_content_type, 'unknown') as file_content_type,
                                    COUNT(*)::int as count
                                FROM files_file
                                WHERE parent_content_type_id = OLD.parent_content_type_id
                                AND parent_object_id = OLD.parent_object_id
                                GROUP BY file_content_type
                            ) counts;

                            EXECUTE format(
                                'UPDATE %I SET files_count = $1
                                WHERE target_content_type_id = $2 AND target_object_id = $3',
                                file_target_table
                            ) USING new_counts, OLD.parent_content_type_id, OLD.parent_object_id;
                        END IF;

                        RETURN OLD;
                    END;
                """,
            ),
        ]

    @classmethod
    def get_graphql_object_type(cls):
        from .graphql.object_types import FileObjectType

        return FileObjectType
