import pytest
import swapper

from baseapp_profiles.tests.factories import ProfileFactory

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


def test_last_message_deleted_clears_fields_when_no_previous():
    room = ChatRoomFactory()
    message = MessageFactory(room=room)

    room.refresh_from_db()
    assert room.last_message_id == message.pk

    message.delete()
    room.refresh_from_db()
    assert room.last_message_id is None
    assert room.last_message_time is None


def test_message_status_are_created():
    room = ChatRoomFactory()
    participants_count = 2
    ChatRoomParticipantFactory.create_batch(participants_count, room=room)

    message = MessageFactory(room=room)

    assert MessageStatus.objects.filter(message=message).count() == participants_count


def test_sender_status_is_read_and_unread_not_counted():
    room = ChatRoomFactory()
    sender_profile = ProfileFactory()
    receiver_profile = ProfileFactory()
    ChatRoomParticipantFactory(room=room, profile=sender_profile)
    ChatRoomParticipantFactory(room=room, profile=receiver_profile)

    message = MessageFactory(
        room=room,
        profile=sender_profile,
        user=sender_profile.owner,
    )

    sender_status = MessageStatus.objects.get(message=message, profile=sender_profile)
    other_status = MessageStatus.objects.get(message=message, profile=receiver_profile)

    assert sender_status.is_read is True
    assert other_status.is_read is False
    assert not UnreadMessageCount.objects.filter(profile=sender_profile, room=room).exists()
    assert UnreadMessageCount.objects.get(profile=receiver_profile, room=room).count == 1


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


def test_unread_message_count_increments_one_at_a_time():
    room = ChatRoomFactory()
    sender = ChatRoomParticipantFactory(room=room)
    receiver = ChatRoomParticipantFactory(room=room)

    MessageFactory(room=room, profile=sender.profile, user=sender.profile.owner)

    unread_count = UnreadMessageCount.objects.get(room=room, profile=receiver.profile)
    assert unread_count.count == 1
    assert not UnreadMessageCount.objects.filter(room=room, profile=sender.profile).exists()

    MessageFactory(room=room, profile=sender.profile, user=sender.profile.owner)

    unread_count.refresh_from_db()
    assert unread_count.count == 2


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


def test_unread_message_count_decrements_one_at_a_time():
    room = ChatRoomFactory()
    participant = ChatRoomParticipantFactory(room=room)
    ChatRoomParticipantFactory(room=room)

    MessageFactory(room=room)
    MessageFactory(room=room)

    unread_count = UnreadMessageCount.objects.get(room=room, profile=participant.profile)
    assert unread_count.count == 2

    status = (
        MessageStatus.objects.filter(
            profile=participant.profile,
            message__room=room,
        )
        .order_by("id")
        .first()
    )
    status.is_read = True
    status.save(update_fields=["is_read"])

    unread_count.refresh_from_db()
    assert unread_count.count == 1
