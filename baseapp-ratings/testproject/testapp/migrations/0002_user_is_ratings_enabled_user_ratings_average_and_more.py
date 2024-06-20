# Generated by Django 5.0.6 on 2024-05-20 15:40

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("testapp", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="is_ratings_enabled",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="user",
            name="ratings_average",
            field=models.FloatField(default=0, editable=False),
        ),
        migrations.AddField(
            model_name="user",
            name="ratings_count",
            field=models.IntegerField(default=0, editable=False),
        ),
        migrations.AddField(
            model_name="user",
            name="ratings_sum",
            field=models.IntegerField(default=0, editable=False),
        ),
    ]