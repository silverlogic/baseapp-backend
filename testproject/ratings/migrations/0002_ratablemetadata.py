import django.db.models.deletion
import django.utils.timezone
import model_utils.fields
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("baseapp_core", "0001_initial"),
        ("ratings", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="RatableMetadata",
            fields=[
                (
                    "created",
                    model_utils.fields.AutoCreatedField(
                        default=django.utils.timezone.now,
                        editable=False,
                        verbose_name="created",
                    ),
                ),
                (
                    "modified",
                    model_utils.fields.AutoLastModifiedField(
                        default=django.utils.timezone.now,
                        editable=False,
                        verbose_name="modified",
                    ),
                ),
                (
                    "target",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        primary_key=True,
                        related_name="ratable_metadata",
                        serialize=False,
                        to="baseapp_core.documentid",
                    ),
                ),
                ("ratings_count", models.IntegerField(default=0, editable=False)),
                ("ratings_sum", models.IntegerField(default=0, editable=False)),
                ("ratings_average", models.FloatField(default=0, editable=False)),
                ("is_ratings_enabled", models.BooleanField(default=True)),
            ],
            options={
                "verbose_name": "ratable metadata",
                "verbose_name_plural": "ratable metadata",
                "abstract": False,
            },
        ),
    ]
