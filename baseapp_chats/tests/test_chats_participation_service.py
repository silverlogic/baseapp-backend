"""Tests for the `chats_participation` shared service.

The service replaces the cross-package code that used to live inline in
`baseapp_auth/rest_framework/users/tasks.py:anonymize_and_delete_user_task` —
that path now goes through `shared_services.get("chats_participation")`
so the auth package has no swapper-loaded chats imports.
"""

import pytest
import swapper

from baseapp_chats.services import ChatsParticipationService
from baseapp_core.plugins import shared_services
from baseapp_core.tests.factories import UserFactory
from baseapp_profiles.tests.factories import ProfileFactory

from .factories import ChatRoomFactory, ChatRoomParticipantFactory

pytestmark = pytest.mark.django_db

ChatRoom = swapper.load_model("baseapp_chats", "ChatRoom")
ChatRoomParticipant = swapper.load_model("baseapp_chats", "ChatRoomParticipant")


def test_service_is_registered():
    """Service is registered by `apps.py.ready()` under the documented name."""
    service = shared_services.get("chats_participation")
    assert service is not None
    assert isinstance(service, ChatsParticipationService)


def test_cleanup_user_participation_removes_only_target_user_rows():
    user = UserFactory()
    other_profile = ProfileFactory()
    room = ChatRoomFactory()
    user_participant = ChatRoomParticipantFactory(profile=user.profile, room=room)
    other_participant = ChatRoomParticipantFactory(profile=other_profile, room=room)
    room.participants_count = 2
    room.save(update_fields=["participants_count"])

    service = shared_services.get("chats_participation")
    service.cleanup_user_participation(user)

    assert not ChatRoomParticipant.objects.filter(pk=user_participant.pk).exists()
    assert ChatRoomParticipant.objects.filter(pk=other_participant.pk).exists()


def test_cleanup_user_participation_recomputes_participants_count():
    user = UserFactory()
    room = ChatRoomFactory()
    ChatRoomParticipantFactory(profile=user.profile, room=room)
    ChatRoomParticipantFactory(profile=ProfileFactory(), room=room)
    ChatRoomParticipantFactory(profile=ProfileFactory(), room=room)
    room.participants_count = 3
    room.save(update_fields=["participants_count"])

    shared_services.get("chats_participation").cleanup_user_participation(user)

    room.refresh_from_db()
    assert room.participants_count == 2


def test_cleanup_user_participation_handles_user_with_no_rooms():
    """Idempotent on a clean user — no DB activity, no exception."""
    user = UserFactory()

    shared_services.get("chats_participation").cleanup_user_participation(user)


def test_cleanup_user_participation_spans_multiple_rooms():
    user = UserFactory()
    room_a = ChatRoomFactory()
    room_b = ChatRoomFactory()
    ChatRoomParticipantFactory(profile=user.profile, room=room_a)
    ChatRoomParticipantFactory(profile=ProfileFactory(), room=room_a)
    ChatRoomParticipantFactory(profile=user.profile, room=room_b)
    ChatRoomParticipantFactory(profile=ProfileFactory(), room=room_b)
    ChatRoomParticipantFactory(profile=ProfileFactory(), room=room_b)
    room_a.participants_count = 2
    room_a.save(update_fields=["participants_count"])
    room_b.participants_count = 3
    room_b.save(update_fields=["participants_count"])

    shared_services.get("chats_participation").cleanup_user_participation(user)

    room_a.refresh_from_db()
    room_b.refresh_from_db()
    assert room_a.participants_count == 1
    assert room_b.participants_count == 2
    assert not ChatRoomParticipant.objects.filter(profile__user=user).exists()
