# Remove files_count and is_files_enabled from Comment model

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("baseapp_comments", "0018_comment_files_count_comment_is_files_enabled"),
        ("baseapp_files", "0003_migrate_data_to_filetarget"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="comment",
            name="files_count",
        ),
        migrations.RemoveField(
            model_name="comment",
            name="is_files_enabled",
        ),
    ]
