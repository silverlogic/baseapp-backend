import pgtrigger
from django.db import models
from pgtrigger import utils


class Func(pgtrigger.Func):
    def render(self, model: models.Model) -> str:
        fields = utils.AttrDict({field.name: field for field in model._meta.fields})
        columns = utils.AttrDict({field.name: field.column for field in model._meta.fields})
        return self.func.format(model=model, meta=model._meta, fields=fields, columns=columns)


def increment_unread_count_trigger(UnreadMessageCount, Message):
    return pgtrigger.Trigger(
        name="increment_unread_count",
        level=pgtrigger.Row,
        when=pgtrigger.After,
        operation=pgtrigger.Insert,
        condition=pgtrigger.Q(new__is_read=False),
        func=f"""
            INSERT INTO {UnreadMessageCount._meta.db_table} (room_id, profile_id, marked_unread, count)
            VALUES ((SELECT room_id FROM {Message._meta.db_table} WHERE id = NEW.message_id), NEW.profile_id, False, 1)
            ON CONFLICT (room_id, profile_id)
            DO UPDATE SET count = {UnreadMessageCount._meta.db_table}.count + 1;
            RETURN NULL;
        """,
    )


def decrement_unread_count_trigger(UnreadMessageCount, Message):
    return pgtrigger.Trigger(
        name="decrement_unread_count",
        level=pgtrigger.Row,
        when=pgtrigger.After,
        operation=pgtrigger.Update,
        condition=pgtrigger.Q(new__is_read=True, old__is_read=False),
        func=f"""
            UPDATE {UnreadMessageCount._meta.db_table}
            SET count = GREATEST(0, count - 1)
            WHERE
                room_id = (SELECT room_id FROM {Message._meta.db_table} WHERE id = NEW.message_id) AND
                profile_id = NEW.profile_id;
            RETURN NULL;
        """,
    )


# Create MessageStatus row in the database for each CharRoomParticipant
def create_message_status_trigger(ChatRoomParticipant, MessageType):
    return pgtrigger.Trigger(
        name="create_message_status",
        level=pgtrigger.Row,
        when=pgtrigger.After,
        operation=pgtrigger.Insert,
        condition=pgtrigger.Q(new__message_type=MessageType.USER_MESSAGE),
        func=Func(
            f"""
            INSERT INTO {{model.statuses.field.model._meta.db_table}} (message_id, profile_id, is_read)
            SELECT NEW.id, crp.profile_id, CASE WHEN NEW.profile_id = crp.profile_id THEN TRUE ELSE FALSE END
            FROM {ChatRoomParticipant._meta.db_table} as crp
            WHERE crp.room_id = NEW.room_id;
            RETURN NULL;
        """
        ),
    )


# Set ChatRoom last_message and last_message_time fields when a new Message is created
def set_last_message_on_insert_trigger(ChatRoom):
    return pgtrigger.Trigger(
        name="set_last_message",
        level=pgtrigger.Row,
        when=pgtrigger.After,
        operation=pgtrigger.Insert,
        func=f"""
            UPDATE {ChatRoom._meta.db_table}
            SET last_message_id = NEW.id, last_message_time = NEW.created
            WHERE id = NEW.room_id;
            RETURN NULL;
        """,
    )


# Update ChatRoom last_message and last_message_time fields to previous message when the last message is deleted
def update_last_message_on_delete_trigger(ChatRoom):
    return pgtrigger.Trigger(
        name="update_last_message",
        level=pgtrigger.Row,
        when=pgtrigger.After,
        operation=pgtrigger.Delete,
        func=Func(
            f"""
            UPDATE {ChatRoom._meta.db_table}
            SET last_message_id = (
                SELECT id
                FROM {{meta.db_table}}
                WHERE room_id = OLD.room_id
                ORDER BY created DESC
                LIMIT 1
            ),
            last_message_time = (
                SELECT created
                FROM {{meta.db_table}}
                WHERE room_id = OLD.room_id
                ORDER BY created DESC
                LIMIT 1
            )
            WHERE id = OLD.room_id;
            RETURN NULL;
        """
        ),
    )
