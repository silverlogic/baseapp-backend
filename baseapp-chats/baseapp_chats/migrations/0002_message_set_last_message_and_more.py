# Generated by Django 4.2.15 on 2024-09-25 15:29

import pgtrigger.compiler
import pgtrigger.migrations
import swapper
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("baseapp_chats", "0001_initial"),
    ]

    operations = filter(
        lambda x: x is not None,
        [
            (
                pgtrigger.migrations.AddTrigger(
                    model_name="message",
                    trigger=pgtrigger.compiler.Trigger(
                        name="set_last_message",
                        sql=pgtrigger.compiler.UpsertTriggerSql(
                            func="\n            UPDATE baseapp_chats_chatroom\n            SET last_message_id = NEW.id, last_message_time = NEW.created\n            WHERE id = NEW.room_id;\n            RETURN NULL;\n        ",
                            hash="06f966e2a58859020db8c4fe063d60775823bc1a",
                            operation="INSERT",
                            pgid="pgtrigger_set_last_message_9c677",
                            table="baseapp_chats_message",
                            when="AFTER",
                        ),
                    ),
                )
                if not swapper.is_swapped("baseapp_chats", "Message")
                else None
            ),
            (
                pgtrigger.migrations.AddTrigger(
                    model_name="message",
                    trigger=pgtrigger.compiler.Trigger(
                        name="create_message_status",
                        sql=pgtrigger.compiler.UpsertTriggerSql(
                            func="\n            INSERT INTO baseapp_chats_messagestatus (message_id, profile_id, is_read)\n            SELECT NEW.id, crp.profile_id, CASE WHEN NEW.profile_id = crp.profile_id THEN TRUE ELSE FALSE END\n            FROM baseapp_chats_chatroomparticipant as crp\n            WHERE crp.room_id = NEW.room_id;\n            RETURN NULL;\n        ",
                            hash="7a38e6c43d86b779e659c95fe1b790016ad3ca54",
                            operation="INSERT",
                            pgid="pgtrigger_create_message_status_c941b",
                            table="baseapp_chats_message",
                            when="AFTER",
                        ),
                    ),
                )
                if not swapper.is_swapped("baseapp_chats", "Message")
                else None
            ),
            (
                pgtrigger.migrations.AddTrigger(
                    model_name="message",
                    trigger=pgtrigger.compiler.Trigger(
                        name="update_last_message",
                        sql=pgtrigger.compiler.UpsertTriggerSql(
                            func="\n            UPDATE baseapp_chats_chatroom\n            SET last_message_id = (\n                SELECT id\n                FROM baseapp_chats_message\n                WHERE room_id = OLD.room_id\n                ORDER BY created DESC\n                LIMIT 1\n            ),\n            last_message_time = (\n                SELECT created\n                FROM baseapp_chats_message\n                WHERE room_id = OLD.room_id\n                ORDER BY created DESC\n                LIMIT 1\n            )\n            WHERE id = OLD.room_id;\n            RETURN NULL;\n        ",
                            hash="185b6146e2a5bbec3fb6668180701954aebaaaa3",
                            operation="DELETE",
                            pgid="pgtrigger_update_last_message_e519b",
                            table="baseapp_chats_message",
                            when="AFTER",
                        ),
                    ),
                )
                if not swapper.is_swapped("baseapp_chats", "Message")
                else None
            ),
            (
                pgtrigger.migrations.AddTrigger(
                    model_name="messagestatus",
                    trigger=pgtrigger.compiler.Trigger(
                        name="increment_unread_count",
                        sql=pgtrigger.compiler.UpsertTriggerSql(
                            condition='WHEN (NOT NEW."is_read")',
                            func="\n            INSERT INTO baseapp_chats_unreadmessagecount (room_id, profile_id, count)\n            VALUES ((SELECT room_id FROM baseapp_chats_message WHERE id = NEW.message_id), NEW.profile_id, 1)\n            ON CONFLICT (room_id, profile_id)\n            DO UPDATE SET count = baseapp_chats_unreadmessagecount.count + 1;\n            RETURN NULL;\n        ",
                            hash="b6b105f4558ddea8d44c7872d91b78510843366b",
                            operation="INSERT",
                            pgid="pgtrigger_increment_unread_count_ec3cd",
                            table="baseapp_chats_messagestatus",
                            when="AFTER",
                        ),
                    ),
                )
                if not swapper.is_swapped("baseapp_chats", "MessageStatus")
                else None
            ),
            (
                pgtrigger.migrations.AddTrigger(
                    model_name="messagestatus",
                    trigger=pgtrigger.compiler.Trigger(
                        name="decrement_unread_count",
                        sql=pgtrigger.compiler.UpsertTriggerSql(
                            condition='WHEN (NEW."is_read" AND NOT OLD."is_read")',
                            func="\n            UPDATE baseapp_chats_unreadmessagecount\n            SET count = GREATEST(0, count - 1)\n            WHERE\n                room_id = (SELECT room_id FROM baseapp_chats_message WHERE id = NEW.message_id) AND\n                profile_id = NEW.profile_id;\n            RETURN NULL;\n        ",
                            hash="08effa83237ad55cf10b5eb25e6fc9e824799b14",
                            operation="UPDATE",
                            pgid="pgtrigger_decrement_unread_count_a1c0b",
                            table="baseapp_chats_messagestatus",
                            when="AFTER",
                        ),
                    ),
                )
                if not swapper.is_swapped("baseapp_chats", "MessageStatus")
                else None
            ),
        ],
    )