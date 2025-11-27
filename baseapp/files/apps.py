import pgtrigger
import swapper
from django.apps import AppConfig


class FilesConfig(AppConfig):
    name = "baseapp.files"
    label = "baseapp_files"
    verbose_name = "BaseApp Files"

    def ready(self):
        # Import here to avoid AppRegistryNotReady errors
        File = swapper.load_model("baseapp_files", "File")
        FileTarget = swapper.load_model("baseapp_files", "FileTarget")

        # Get table names
        file_table = File._meta.db_table
        file_target_table = FileTarget._meta.db_table

        # Register triggers programmatically with actual table names
        pgtrigger.register(
            pgtrigger.Trigger(
                name="update_file_target_on_insert",
                operation=pgtrigger.Insert,
                when=pgtrigger.After,
                func=f"""
                    DECLARE
                        new_counts JSONB;
                    BEGIN
                        IF NEW.parent_content_type_id IS NOT NULL AND NEW.parent_object_id IS NOT NULL THEN
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
                                WHERE parent_content_type_id = NEW.parent_content_type_id
                                AND parent_object_id = NEW.parent_object_id
                                GROUP BY file_content_type
                            ) counts;

                            -- Insert or update FileTarget
                            INSERT INTO {file_target_table} (target_content_type_id, target_object_id, files_count, is_files_enabled)
                            VALUES (NEW.parent_content_type_id, NEW.parent_object_id, new_counts, true)
                            ON CONFLICT (target_content_type_id, target_object_id)
                            DO UPDATE SET files_count = new_counts;
                        END IF;
                        RETURN NEW;
                    END;
                """,
            )
        )(File)

        pgtrigger.register(
            pgtrigger.Trigger(
                name="update_file_target_on_update",
                operation=pgtrigger.Update,
                when=pgtrigger.After,
                func=f"""
                    DECLARE
                        new_counts JSONB;
                        old_counts JSONB;
                    BEGIN
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
                                '{{"total": 0}}'::jsonb
                            ) INTO old_counts
                            FROM (
                                SELECT
                                    COALESCE(file_content_type, 'unknown') as file_content_type,
                                    COUNT(*)::int as count
                                FROM {file_table}
                                WHERE parent_content_type_id = OLD.parent_content_type_id
                                AND parent_object_id = OLD.parent_object_id
                                GROUP BY file_content_type
                            ) counts;

                            UPDATE {file_target_table} SET files_count = old_counts
                            WHERE target_content_type_id = OLD.parent_content_type_id
                            AND target_object_id = OLD.parent_object_id;
                        END IF;

                        -- Update new parent
                        IF NEW.parent_content_type_id IS NOT NULL AND NEW.parent_object_id IS NOT NULL THEN
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
                                WHERE parent_content_type_id = NEW.parent_content_type_id
                                AND parent_object_id = NEW.parent_object_id
                                GROUP BY file_content_type
                            ) counts;

                            INSERT INTO {file_target_table} (target_content_type_id, target_object_id, files_count, is_files_enabled)
                            VALUES (NEW.parent_content_type_id, NEW.parent_object_id, new_counts, true)
                            ON CONFLICT (target_content_type_id, target_object_id)
                            DO UPDATE SET files_count = new_counts;
                        END IF;

                        RETURN NEW;
                    END;
                """,
            )
        )(File)

        pgtrigger.register(
            pgtrigger.Trigger(
                name="update_file_target_on_delete",
                operation=pgtrigger.Delete,
                when=pgtrigger.After,
                func=f"""
                    DECLARE
                        new_counts JSONB;
                    BEGIN
                        IF OLD.parent_content_type_id IS NOT NULL AND OLD.parent_object_id IS NOT NULL THEN
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
                                WHERE parent_content_type_id = OLD.parent_content_type_id
                                AND parent_object_id = OLD.parent_object_id
                                GROUP BY file_content_type
                            ) counts;

                            UPDATE {file_target_table} SET files_count = new_counts
                            WHERE target_content_type_id = OLD.parent_content_type_id
                            AND target_object_id = OLD.parent_object_id;
                        END IF;

                        RETURN OLD;
                    END;
                """,
            )
        )(File)
