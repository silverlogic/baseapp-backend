from collections.abc import Iterable
from typing import Any, Optional

import strawberry
import strawberry_django
import swapper
from django.db.models import Model
from django_filters.filterset import filterset_factory
from strawberry.types import Info

from baseapp_core.plugins import strawberry_shared_interfaces
from baseapp_core.strawberry import CountedConnection, Node, django_type, type_for_model
from baseapp_core.strawberry.connections import connection
from baseapp_core.strawberry.enums import enum_from_choices
from baseapp_core.strawberry.scalars import JSONString

from ..graphql.filters import ChatRoomFilter, ChatRoomParticipantFilter
from ..graphql.object_types import BaseChatRoomObjectType, BaseMessageObjectType

ChatRoom = swapper.load_model("baseapp_chats", "ChatRoom")
ChatRoomParticipant = swapper.load_model("baseapp_chats", "ChatRoomParticipant")
UnreadMessageCount = swapper.load_model("baseapp_chats", "UnreadMessageCount")
Message = swapper.load_model("baseapp_chats", "Message")

ChatRoomLazyType = type_for_model(ChatRoom)
ChatRoomParticipantLazyType = type_for_model(ChatRoomParticipant)
UnreadMessageCountLazyType = type_for_model(UnreadMessageCount)
MessageLazyType = type_for_model(Message)

ChatRoomParticipantRolesEnum = enum_from_choices(
    ChatRoomParticipant.ChatRoomParticipantRoles, "ChatRoomParticipantRoles"
)
VerbsEnum = enum_from_choices(Message.Verbs, "Verbs")
MessageTypeEnum = enum_from_choices(Message.MessageType, "MessageType")

# Graphene built this from `Meta.filter_fields = ("verb",)`.
MessageFilter = filterset_factory(Message, fields=["verb"])


@django_type(
    ChatRoomParticipant,
    filterset_class=ChatRoomParticipantFilter,
    relations=("profile",),
)
class ChatRoomParticipantType(Node):
    has_archived_room: strawberry.auto
    role: ChatRoomParticipantRolesEnum | None


@django_type(UnreadMessageCount)
class UnreadMessageCountType(Node):
    count: strawberry.auto
    marked_unread: strawberry.auto


# room_id: the prefetch pipeline maps messages back to their room; deleted, message_type,
# profile_id: `content` branches on them.
@django_type(
    Message,
    filterset_class=MessageFilter,
    relations=("user", "profile", "room", "in_reply_to"),
    only=["room_id", "deleted", "message_type", "profile_id", "extra_data", "content"],
)
class MessageType(*strawberry_shared_interfaces.get("MentionsInterface"), Node):
    created: strawberry.auto
    deleted: strawberry.auto
    message_type: MessageTypeEnum | None
    verb: VerbsEnum | None
    extra_data: JSONString | None

    @strawberry_django.field
    def content(self, info: Info, profile_id: strawberry.ID | None = None) -> str | None:
        return BaseMessageObjectType.resolve_content(self, info, profile_id=profile_id)

    @strawberry_django.field
    def is_read(self, info: Info, profile_id: strawberry.ID | None = None) -> bool | None:
        return BaseMessageObjectType.resolve_is_read(self, info, profile_id=profile_id)

    @strawberry_django.field(only=["action_object_content_type_id", "action_object_object_id"])
    def action_object(self, info: Info) -> Node | None:
        return self.action_object

    @classmethod
    def get_node(cls, info: Info, pk: Any) -> Model | None:
        message = Message.objects.filter(id=pk).first()
        if message is None or not info.context.user.has_perm("baseapp_chats.view_message", message):
            return None
        return message


@django_type(ChatRoom, filterset_class=ChatRoomFilter, relations=("last_message",))
class ChatRoomType(Node):
    last_message_time: strawberry.auto
    participants_count: strawberry.auto
    is_group: strawberry.auto

    @strawberry_django.field(only=["title", "is_group"])
    def title(self, info: Info) -> str | None:
        return BaseChatRoomObjectType.resolve_title(self, info)

    @strawberry_django.field(only=["image", "is_group"])
    def image(self, info: Info, width: int, height: int) -> str | None:
        from baseapp_core.strawberry.fields import build_thumbnail_url

        file = BaseChatRoomObjectType.resolve_image(self, info)
        return build_thumbnail_url(file, info, width, height)

    @connection(
        CountedConnection[ChatRoomParticipantLazyType] | None,
        filterset_class=ChatRoomParticipantFilter,
    )
    def participants(self, info: Info) -> Iterable[Model]:
        return BaseChatRoomObjectType.resolve_participants(self, info)

    @connection(CountedConnection[MessageLazyType] | None, filterset_class=MessageFilter)
    def all_messages(self, info: Info) -> Iterable[Model]:
        return BaseChatRoomObjectType.resolve_all_messages(self, info)

    @strawberry.field(graphql_type=Optional[UnreadMessageCountLazyType])
    def unread_messages(self, info: Info, profile_id: strawberry.ID | None = None) -> Any:
        return BaseChatRoomObjectType.resolve_unread_messages(self, info, profile_id=profile_id)

    @strawberry_django.field
    def is_archived(self, info: Info, profile_id: strawberry.ID | None = None) -> bool | None:
        return BaseChatRoomObjectType.resolve_is_archived(self, info, profile_id=profile_id)

    @strawberry.field(graphql_type=Optional[ChatRoomParticipantLazyType])
    def other_participant(self, info: Info) -> Any:
        return BaseChatRoomObjectType.resolve_other_participant(self, info)

    @strawberry_django.field
    def is_sole_admin(self, info: Info) -> bool | None:
        return BaseChatRoomObjectType.resolve_is_sole_admin(self, info)

    @strawberry_django.field
    def participant_ids(self, info: Info) -> list[strawberry.ID | None] | None:
        return BaseChatRoomObjectType.resolve_participant_ids(self, info)

    @strawberry_django.field(description="Whether the given profile is a participant of this room.")
    def is_participant(self, info: Info, profile_id: strawberry.ID) -> bool | None:
        return BaseChatRoomObjectType.resolve_is_participant(self, info, profile_id=profile_id)

    @classmethod
    def get_node(cls, info: Info, pk: Any) -> Model | None:
        room = ChatRoom.objects.filter(id=pk).first()
        if room is None or not info.context.user.has_perm("baseapp_chats.view_chatroom", room):
            return None
        return room
