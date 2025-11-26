# Generated migration for FileTarget model

import baseapp.files.utils
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("baseapp_files", "0001_initial"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [
        migrations.CreateModel(
            name="FileTarget",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("target_object_id", models.PositiveIntegerField(db_index=True)),
                (
                    "files_count",
                    models.JSONField(default=baseapp.files.utils.default_files_count),
                ),
                (
                    "is_files_enabled",
                    models.BooleanField(default=True, verbose_name="is files enabled"),
                ),
                (
                    "target_content_type",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="contenttypes.contenttype",
                        db_index=True,
                    ),
                ),
            ],
            options={
                "abstract": False,
                "swappable": "BASEAPP_FILES_FILETARGET_MODEL",
                "unique_together": {("target_content_type", "target_object_id")},
            },
        ),
        migrations.AddIndex(
            model_name="filetarget",
            index=models.Index(
                fields=["target_content_type", "target_object_id"],
                name="baseapp_fil_target__9f3b9c_idx",
            ),
        ),
    ]
