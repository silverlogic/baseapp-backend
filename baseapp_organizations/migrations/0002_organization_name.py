# Generated by Django 5.0.11 on 2025-03-13 15:56

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("baseapp_organizations", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="organization",
            name="name",
            field=models.CharField(blank=True, max_length=255, null=True, verbose_name="name"),
        ),
    ]
