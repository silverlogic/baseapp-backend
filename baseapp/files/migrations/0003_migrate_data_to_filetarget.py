# Data migration to populate FileTarget from existing fileable models

from django.db import migrations
from django.contrib.contenttypes.models import ContentType


def migrate_comment_data_to_filetarget(apps, schema_editor):
    """Migrate files_count and is_files_enabled from Comment to FileTarget"""
    try:
        Comment = apps.get_model("baseapp_comments", "Comment")
        FileTarget = apps.get_model("baseapp_files", "FileTarget")

        comment_content_type = ContentType.objects.get_for_model(Comment)

        for comment in Comment.objects.all():
            FileTarget.objects.update_or_create(
                target_content_type=comment_content_type,
                target_object_id=comment.pk,
                defaults={
                    "files_count": comment.files_count if hasattr(comment, 'files_count') else {"total": 0},
                    "is_files_enabled": comment.is_files_enabled if hasattr(comment, 'is_files_enabled') else True,
                }
            )
    except Exception:
        pass


def reverse_migration(apps, schema_editor):
    """Reverse migration - copy data back from FileTarget to Comment"""
    try:
        Comment = apps.get_model("baseapp_comments", "Comment")
        FileTarget = apps.get_model("baseapp_files", "FileTarget")

        comment_content_type = ContentType.objects.get_for_model(Comment)

        file_targets = FileTarget.objects.filter(target_content_type=comment_content_type)
        for file_target in file_targets:
            try:
                comment = Comment.objects.get(pk=file_target.target_object_id)
                if hasattr(comment, 'files_count'):
                    comment.files_count = file_target.files_count
                if hasattr(comment, 'is_files_enabled'):
                    comment.is_files_enabled = file_target.is_files_enabled
                comment.save(update_fields=['files_count', 'is_files_enabled'])
            except Comment.DoesNotExist:
                pass
    except Exception:
        pass


class Migration(migrations.Migration):

    dependencies = [
        ("baseapp_files", "0002_filetarget"),
        ("baseapp_comments", "0018_comment_files_count_comment_is_files_enabled"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [
        migrations.RunPython(migrate_comment_data_to_filetarget, reverse_migration),
    ]
