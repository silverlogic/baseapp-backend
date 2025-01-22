# Generated by Django 5.0.8 on 2025-01-21 11:57

import django.db.models.deletion
import pgtrigger.compiler
import pgtrigger.migrations
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("baseapp_chats", "0008_alter_chatroomparticipant_options"),
        migrations.swappable_dependency(settings.BASEAPP_PROFILES_PROFILE_MODEL),
    ]

    operations = [
        pgtrigger.migrations.RemoveTrigger(
            model_name="message",
            name="create_message_status",
        ),
        migrations.AddField(
            model_name="message",
            name="content_linked_profile_actor",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="linked_as_content_actor_set",
                to=settings.BASEAPP_PROFILES_PROFILE_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="message",
            name="content_linked_profile_target",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="linked_as_content_target_set",
                to=settings.BASEAPP_PROFILES_PROFILE_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="message",
            name="message_type",
            field=models.IntegerField(
                choices=[(1, "User message"), (2, "System message")], default=1
            ),
        ),
        pgtrigger.migrations.AddTrigger(
            model_name="message",
            trigger=pgtrigger.compiler.Trigger(
                name="create_message_status",
                sql=pgtrigger.compiler.UpsertTriggerSql(
                    condition='WHEN (NEW."message_type" = 1)',
                    func="\n            INSERT INTO baseapp_chats_messagestatus (message_id, profile_id, is_read)\n            SELECT NEW.id, crp.profile_id, CASE WHEN NEW.profile_id = crp.profile_id THEN TRUE ELSE FALSE END\n            FROM baseapp_chats_chatroomparticipant as crp\n            WHERE crp.room_id = NEW.room_id;\n            RETURN NULL;\n        ",
                    hash="beb46ab0586aff0156230e06f0f378f3af30b54b",
                    operation="INSERT",
                    pgid="pgtrigger_create_message_status_c941b",
                    table="baseapp_chats_message",
                    when="AFTER",
                ),
            ),
        ),
    ]
