from __future__ import annotations

import swapper
from django.apps import apps

from baseapp_core.plugins import SharedServiceProvider


class ChatsParticipationService(SharedServiceProvider):
    """Expose chat participation cleanup to other packages.

    Consumers (currently only the auth anonymize-user task) call
    `shared_services.get("chats_participation").cleanup_user_participation(user)`
    so the dependency stays one-way and chats can be uninstalled without
    leaving callers with broken swapper imports.
    """

    @property
    def service_name(self) -> str:
        return "chats_participation"

    def is_available(self) -> bool:
        return apps.is_installed("baseapp_chats")

    def cleanup_user_participation(self, user) -> None:
        ChatRoomParticipant = swapper.load_model("baseapp_chats", "ChatRoomParticipant")
        ChatRoom = swapper.load_model("baseapp_chats", "ChatRoom")

        participant_qs = ChatRoomParticipant.objects.filter(profile__user=user)
        room_ids = list(participant_qs.values_list("room_id", flat=True).distinct())
        participant_qs.delete()

        for room_id in room_ids:
            room = ChatRoom.objects.get(id=room_id)
            room.participants_count = ChatRoomParticipant.objects.filter(room=room).count()
            room.save(update_fields=["participants_count"])
