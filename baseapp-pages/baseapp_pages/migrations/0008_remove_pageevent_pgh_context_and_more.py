# Generated by Django 5.0.3 on 2024-12-09 18:58

import pgtrigger.migrations
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("baseapp_pages", "0007_alter_metadataevent_pgh_context_and_more"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="pageevent",
            name="pgh_context",
        ),
        migrations.RemoveField(
            model_name="pageevent",
            name="pgh_obj",
        ),
        migrations.RemoveField(
            model_name="pageevent",
            name="user",
        ),
        pgtrigger.migrations.RemoveTrigger(
            model_name="page",
            name="insert_insert",
        ),
        pgtrigger.migrations.RemoveTrigger(
            model_name="page",
            name="update_update",
        ),
        pgtrigger.migrations.RemoveTrigger(
            model_name="page",
            name="delete_delete",
        ),
        migrations.DeleteModel(
            name="PageEvent",
        ),
    ]
