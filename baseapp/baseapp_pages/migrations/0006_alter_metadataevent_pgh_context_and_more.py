# Generated by Django 4.2.15 on 2024-09-03 13:52

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("pghistory", "0006_delete_aggregateevent"),
        ("baseapp_pages", "0005_remove_metadata_snapshot_insert_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="metadataevent",
            name="pgh_context",
            field=models.ForeignKey(
                db_constraint=False,
                null=True,
                on_delete=django.db.models.deletion.DO_NOTHING,
                related_name="+",
                related_query_name="+",
                to="pghistory.context",
            ),
        ),
        migrations.AlterField(
            model_name="metadataevent",
            name="pgh_obj",
            field=models.ForeignKey(
                db_constraint=False,
                on_delete=django.db.models.deletion.DO_NOTHING,
                related_name="events",
                related_query_name="+",
                to="baseapp_pages.metadata",
            ),
        ),
        migrations.AlterField(
            model_name="pageevent",
            name="pgh_context",
            field=models.ForeignKey(
                db_constraint=False,
                null=True,
                on_delete=django.db.models.deletion.DO_NOTHING,
                related_name="+",
                related_query_name="+",
                to="pghistory.context",
            ),
        ),
        migrations.AlterField(
            model_name="pageevent",
            name="pgh_obj",
            field=models.ForeignKey(
                db_constraint=False,
                on_delete=django.db.models.deletion.DO_NOTHING,
                related_name="events",
                related_query_name="+",
                to=settings.BASEAPP_PAGES_PAGE_MODEL,
            ),
        ),
    ]
