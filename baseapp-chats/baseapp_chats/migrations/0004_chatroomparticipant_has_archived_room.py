# Generated by Django 5.0.9 on 2024-12-09 14:07

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("baseapp_chats", "0003_alter_unreadmessagecount_room"),
    ]

    operations = [
        migrations.AddField(
            model_name="chatroomparticipant",
            name="has_archived_room",
            field=models.BooleanField(default=False),
        ),
    ]
