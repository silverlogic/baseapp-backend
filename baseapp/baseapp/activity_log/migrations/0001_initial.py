# Generated by Django 5.0.1 on 2024-11-03 00:29

from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("pghistory", "0006_delete_aggregateevent"),
    ]

    operations = [
        migrations.CreateModel(
            name="ActivityLog",
            fields=[],
            options={
                "proxy": True,
                "indexes": [],
                "constraints": [],
            },
            bases=("pghistory.context", models.Model),
        ),
    ]
