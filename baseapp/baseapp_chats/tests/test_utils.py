import pytest
import swapper

from .factories import ChatRoomFactory, ChatRoomParticipantFactory, MessageFactory

pytestmark = pytest.mark.django_db

ChatRoom = swapper.load_model("baseapp_chats", "ChatRoom")
Message = swapper.load_model("baseapp_chats", "Message")
ChatRoomParticipant = swapper.load_model("baseapp_chats", "ChatRoomParticipant")
UnreadMessageCount = swapper.load_model("baseapp_chats", "UnreadMessageCount")
MessageStatus = swapper.load_model("baseapp_chats", "MessageStatus")


def test_last_message_is_set():
    room = ChatRoomFactory()
    message = MessageFactory(room=room)

    room.refresh_from_db()
    assert room.last_message == message
    assert room.last_message_time == message.created


def test_last_message_deleted_updates_to_previous():
    room = ChatRoomFactory()
    old_message = MessageFactory(room=room)
    new_message = MessageFactory(room=room)

    room.refresh_from_db()
    assert room.last_message_id == new_message.pk
    assert room.last_message_time == new_message.created

    new_message.delete()
    room.refresh_from_db()
    assert room.last_message_id == old_message.pk
    assert room.last_message_time == old_message.created


def test_message_status_are_created():
    room = ChatRoomFactory()
    participants_count = 2
    ChatRoomParticipantFactory.create_batch(participants_count, room=room)

    message = MessageFactory(room=room)

    assert MessageStatus.objects.filter(message=message).count() == participants_count


def test_does_not_create_message_status_for_system_messages():
    room = ChatRoomFactory()
    participants_count = 2
    ChatRoomParticipantFactory.create_batch(participants_count, room=room)

    message = MessageFactory(room=room, message_type=Message.MessageType.SYSTEM_GENERATED)

    assert MessageStatus.objects.filter(message=message).count() == 0


def test_unread_message_count_is_incremented():
    room = ChatRoomFactory()
    participants_count = 2
    participants = ChatRoomParticipantFactory.create_batch(participants_count, room=room)

    MessageFactory(room=room)

    for participant in participants:
        assert UnreadMessageCount.objects.get(profile=participant.profile).count == 1


def test_unread_message_count_is_not_incremented_for_system_messages():
    room = ChatRoomFactory()
    participants_count = 2
    participants = ChatRoomParticipantFactory.create_batch(participants_count, room=room)

    MessageFactory(room=room, message_type=Message.MessageType.SYSTEM_GENERATED)

    for participant in participants:
        assert UnreadMessageCount.objects.filter(profile=participant.profile).count() == 0


def test_unread_message_count_is_decremented():
    room = ChatRoomFactory()
    participants_count = 2
    participants = ChatRoomParticipantFactory.create_batch(participants_count, room=room)

    message = MessageFactory(room=room)

    message.statuses.all().update(is_read=True)

    for participant in participants:
        assert UnreadMessageCount.objects.get(profile=participant.profile).count == 0
