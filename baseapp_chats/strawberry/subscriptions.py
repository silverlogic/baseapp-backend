from collections.abc import AsyncGenerator
from typing import Any

import strawberry
import swapper
from channels.db import database_sync_to_async
from strawberry.types import Info

from baseapp_core.graphql import get_obj_from_relay_id, get_pk_from_relay_id
from baseapp_core.strawberry import type_for_model
from baseapp_core.strawberry.connections import Edge
from baseapp_core.strawberry.subscriptions import listen, subscription_group

from .types import ChatRoomLazyType, ChatRoomParticipantLazyType, MessageLazyType

Profile = swapper.load_model("baseapp_profiles", "Profile")
profile_app_label = Profile._meta.app_label


@strawberry.type(name="ChatRoomOnMessage")
class ChatRoomOnMessage:
    message: Edge[MessageLazyType] | None = None


@strawberry.type(name="ChatRoomOnRoomUpdate")
class ChatRoomOnRoomUpdate:
    room: Edge[ChatRoomLazyType] | None = None
    removed_participants: list[ChatRoomParticipantLazyType | None] | None = None
    added_participants: list[ChatRoomParticipantLazyType | None] | None = None


@strawberry.type(name="ChatRoomOnMessagesCountUpdate")
class ChatRoomOnMessagesCountUpdate:
    profile: type_for_model(Profile) | None = None


def _usable_profile(info: Info, profile_id: str) -> Any:
    user = info.context.user
    profile = get_obj_from_relay_id(info, profile_id)
    if not user.is_authenticated or not profile:
        return None
    if not user.has_perm(f"{profile_app_label}.use_profile", profile):
        return None
    return profile


def _on_message_groups(info: Info, room_id: str, profile_id: str) -> list[str]:
    room = get_obj_from_relay_id(info, room_id)
    profile = _usable_profile(info, profile_id)
    if not profile or not room:
        return []
    if not room.participants.filter(profile=profile).exists():
        return []
    if not info.context.user.has_perm("baseapp_chats.view_chatroom", room):
        return []
    return [room_id]


@strawberry.type
class ChatsSubscriptions:
    @strawberry.subscription
    async def chat_room_on_message(
        self, info: Info, room_id: strawberry.ID, profile_id: strawberry.ID
    ) -> AsyncGenerator[ChatRoomOnMessage | None, None]:
        groups = await database_sync_to_async(_on_message_groups)(info, room_id, profile_id)
        if not groups:
            return
        profile_pk = await database_sync_to_async(get_pk_from_relay_id)(profile_id)
        channel_groups = [subscription_group("ChatRoomOnMessage", g) for g in groups]
        async for payload in listen(info, channel_groups):
            message = payload.get("message")
            if not info.context.user.is_authenticated or message is None:
                continue
            if str(message.profile_id) == str(profile_pk):
                continue
            yield ChatRoomOnMessage(message=Edge(node=message, cursor=None))

    @strawberry.subscription
    async def chat_room_on_room_update(
        self, info: Info, profile_id: strawberry.ID
    ) -> AsyncGenerator[ChatRoomOnRoomUpdate | None, None]:
        profile = await database_sync_to_async(_usable_profile)(info, profile_id)
        if not profile:
            return
        channel_groups = [subscription_group("ChatRoomOnRoomUpdate", str(profile.pk))]
        async for payload in listen(info, channel_groups):
            yield ChatRoomOnRoomUpdate(
                room=Edge(node=payload["room"], cursor=None),
                removed_participants=payload["removed_participants"],
                added_participants=payload["added_participants"],
            )

    @strawberry.subscription
    async def chat_room_on_messages_count_update(
        self, info: Info, profile_id: strawberry.ID
    ) -> AsyncGenerator[ChatRoomOnMessagesCountUpdate | None, None]:
        profile = await database_sync_to_async(_usable_profile)(info, profile_id)
        if not profile:
            return
        channel_groups = [subscription_group("ChatRoomOnMessagesCountUpdate", profile_id)]
        async for payload in listen(info, channel_groups):
            yield ChatRoomOnMessagesCountUpdate(profile=payload["profile"])
