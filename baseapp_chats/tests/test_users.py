import pytest
import swapper
from django.contrib.auth import get_user_model

from baseapp_core.tests.factories import UserFactory

from .factories import ChatRoomFactory, ChatRoomParticipantFactory, MessageFactory

pytestmark = pytest.mark.django_db

User = get_user_model()
ChatRoom = swapper.load_model("baseapp_chats", "ChatRoom")
Message = swapper.load_model("baseapp_chats", "Message")
ChatRoomParticipant = swapper.load_model("baseapp_chats", "ChatRoomParticipant")


def test_delete_user_with_message():
    user = UserFactory()
    user_id = user.pk
    room = ChatRoomFactory()
    participants_count = 2
    ChatRoomParticipantFactory.create_batch(participants_count, room=room)
    MessageFactory.create_batch(2, user=user, room=room)

    assert Message.objects.filter(user_id=user_id).count() == 2
    user.delete()
    assert Message.objects.filter(user_id=user_id).count() == 0
    assert Message.objects.count() == 2
