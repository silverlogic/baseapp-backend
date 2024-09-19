# Generated by Django 4.2.15 on 2024-09-10 20:29

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("pghistory", "0006_delete_aggregateevent"),
        ("baseapp_comments", "0014_alter_commentevent_pgh_context_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="commentevent",
            name="pgh_context",
            field=models.ForeignKey(
                db_constraint=False,
                null=True,
                on_delete=django.db.models.deletion.DO_NOTHING,
                related_name="+",
                to="pghistory.context",
            ),
        ),
        migrations.AlterField(
            model_name="commentevent",
            name="pgh_obj",
            field=models.ForeignKey(
                db_constraint=False,
                on_delete=django.db.models.deletion.DO_NOTHING,
                related_name="events",
                to=settings.BASEAPP_COMMENTS_COMMENT_MODEL,
            ),
        ),
    ]