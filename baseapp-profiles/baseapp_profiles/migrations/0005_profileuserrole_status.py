# Generated by Django 4.2.16 on 2024-10-17 18:00

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("baseapp_profiles", "0004_profile_biography"),
    ]

    operations = [
        migrations.AddField(
            model_name="profileuserrole",
            name="status",
            field=models.IntegerField(
                choices=[(1, "active"), (2, "pending"), (3, "inactive")], default=2
            ),
        ),
    ]
