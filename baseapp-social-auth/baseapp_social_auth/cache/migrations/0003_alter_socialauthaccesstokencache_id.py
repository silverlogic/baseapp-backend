# Generated by Django 3.2.19 on 2023-07-18 12:23

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("cache", "0002_alter_socialauthaccesstokencache_id"),
    ]

    operations = [
        migrations.AlterField(
            model_name="socialauthaccesstokencache",
            name="id",
            field=models.BigAutoField(
                auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
            ),
        ),
    ]