# Generated by Django 5.0.6 on 2024-05-20 15:40

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("baseapp_ratings", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="rate",
            name="target_object_id",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
    ]
