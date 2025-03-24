# Generated by Django 5.0.8 on 2025-03-21 17:04

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("baseapp_wagtail_medias", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="customimage",
            name="description",
            field=models.CharField(
                blank=True, default="", max_length=255, verbose_name="description"
            ),
        ),
        migrations.AlterField(
            model_name="customdocument",
            name="file_size",
            field=models.PositiveBigIntegerField(editable=False, null=True),
        ),
    ]
