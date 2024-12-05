# Generated by Django 5.0.9 on 2024-11-13 23:31

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("baseapp_chats", "0002_message_set_last_message_and_more"),
        migrations.swappable_dependency(settings.BASEAPP_CHATS_CHATROOM_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name="unreadmessagecount",
            name="room",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="unread_messages",
                to=settings.BASEAPP_CHATS_CHATROOM_MODEL,
            ),
        ),
    ]
