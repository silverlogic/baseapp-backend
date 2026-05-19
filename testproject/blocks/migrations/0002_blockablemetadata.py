import django.db.models.deletion
import django.utils.timezone
import model_utils.fields
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("baseapp_core", "0001_initial"),
        ("blocks", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="BlockableMetadata",
            fields=[
                (
                    "created",
                    model_utils.fields.AutoCreatedField(
                        default=django.utils.timezone.now, editable=False, verbose_name="created"
                    ),
                ),
                (
                    "modified",
                    model_utils.fields.AutoLastModifiedField(
                        default=django.utils.timezone.now, editable=False, verbose_name="modified"
                    ),
                ),
                (
                    "target",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        primary_key=True,
                        related_name="blockable_metadata",
                        serialize=False,
                        to="baseapp_core.documentid",
                    ),
                ),
                ("blockers_count", models.PositiveIntegerField(default=0, editable=False)),
                ("blocking_count", models.PositiveIntegerField(default=0, editable=False)),
            ],
            options={
                "verbose_name": "blockable metadata",
                "verbose_name_plural": "blockable metadata",
                "abstract": False,
                "swappable": "BASEAPP_BLOCKS_BLOCKABLEMETADATA_MODEL",
            },
        ),
    ]
