# Generated by Django 4.2.11 on 2024-03-19 21:38

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("baseapp_reports", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="report",
            name="report_type",
            field=models.IntegerField(
                blank=True,
                choices=[(1, "Spam"), (2, "Inappropriate"), (3, "Fake"), (4, "Other")],
                null=True,
            ),
        ),
    ]
