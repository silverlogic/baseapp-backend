# Generated by Django 5.0.1 on 2024-06-04 01:32

import pgtrigger.migrations
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("baseapp_comments", "0006_remove_comment_snapshot_insert_and_more"),
    ]

    operations = [
        pgtrigger.migrations.RemoveTrigger(
            model_name="comment",
            name="insert_insert",
        ),
        pgtrigger.migrations.RemoveTrigger(
            model_name="comment",
            name="update_update",
        ),
        pgtrigger.migrations.RemoveTrigger(
            model_name="comment",
            name="delete_delete",
        ),
    ]
