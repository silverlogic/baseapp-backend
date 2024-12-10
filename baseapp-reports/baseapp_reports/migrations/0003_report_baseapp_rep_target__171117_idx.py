# Generated by Django 5.0.1 on 2024-12-11 01:17

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("baseapp_reports", "0002_alter_report_report_type"),
        ("contenttypes", "0002_remove_content_type_name"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddIndex(
            model_name="report",
            index=models.Index(
                fields=["target_content_type", "target_object_id"],
                name="baseapp_rep_target__171117_idx",
            ),
        ),
    ]
