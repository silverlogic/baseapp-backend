# Generated by Django 5.0.1 on 2024-07-11 13:21

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("testapp", "0010_user_profile"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="preferred_language",
            field=models.CharField(
                choices=[("en", "English"), ("es", "Spanish"), ("pt", "Portuguese")],
                default="en",
                max_length=9,
            ),
        ),
    ]