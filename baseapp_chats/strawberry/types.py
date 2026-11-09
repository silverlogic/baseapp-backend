from collections.abc import Iterable
from typing import Any, Optional

import strawberry
import strawberry_django
import swapper
from django.db.models import Case, Model, When
from django.utils.translation import gettext_lazy as _
from django_filters.filterset import filterset_factory
from strawberry.types import Info
from strawberry_django.resolvers import django_resolver

from baseapp_core.graphql import get_obj_relay_id, get_pk_from_relay_id
from baseapp_core.plugins import strawberry_shared_interfaces
from baseapp_core.strawberry import CountedConnection, Node, django_type, type_for_model
from baseapp_core.strawberry.connections import connection
from baseapp_core.strawberry.enums import enum_from_choices
from baseapp_core.strawberry.scalars import JSONString

from ..filters import ChatRoomFilter, ChatRoomParticipantFilter

Profile = swapper.load_model("baseapp_profiles", "Profile")
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


def _current_profile(info: Info) -> Any:
    user = info.context.user
    if hasattr(user, "current_profile"):
        return user.current_profile
    return getattr(user, "profile", None)


def _profile_pk(info: Info, profile_id: str | None = None) -> int | None:
    """`profile_id` when the user is a member of it, else the current profile's pk."""
    user = info.context.user
    if profile_id:
        profile_pk = get_pk_from_relay_id(profile_id)
        if not Profile.objects.get_if_member(pk=profile_pk, user=user):
            return None
        return profile_pk
    if hasattr(user, "current_profile") and hasattr(user.current_profile, "pk"):
        return user.current_profile.pk
    if hasattr(user, "profile") and hasattr(user.profile, "pk"):
        return user.profile.pk
    return None


def _replaced_profile_name(
    profile: Any, profile_pk: int, replacement_text: str, include_verb: bool = False
) -> str:
    if not profile:
        return _("Profile Not Found")
    if profile.id == profile_pk:
        return replacement_text if not include_verb else replacement_text + " are"
    return profile.name if not include_verb else profile.name + " is"


def _other_participant(room: Model, info: Info) -> Any:
    current_profile = _current_profile(info)
    if not current_profile:
        return None
    return room.participants.exclude(profile_id=current_profile.pk).first()


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
        profile_pk = _profile_pk(info, profile_id)
        if not profile_pk:
            return None
        if self.deleted:
            if profile_pk == self.profile.pk:
                return "You deleted this message"
            return "This message was deleted"
        if self.message_type == Message.MessageType.USER_MESSAGE:
            return self.content

        include_verb = (self.extra_data or {}).get("include_verb", False)
        linked_capital_name = _replaced_profile_name(
            self.content_linked_profile_actor, profile_pk, "You", include_verb=include_verb
        )
        linked_small_name = _replaced_profile_name(
            self.content_linked_profile_target,
            profile_pk,
            "You" if include_verb else "you",
            include_verb=include_verb,
        )
        return self.content.format(
            content_linked_profile_actor=linked_capital_name,
            content_linked_profile_target=linked_small_name,
        )

    @strawberry_django.field
    def is_read(self, info: Info, profile_id: strawberry.ID | None = None) -> bool | None:
        profile_pk = _profile_pk(info, profile_id)
        if not profile_pk:
            return None
        message_status = self.statuses.filter(profile_id=profile_pk).first()
        return message_status and message_status.is_read

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
        if self.is_group:
            return self.title
        other_participant = _other_participant(self, info)
        if other_participant and other_participant.profile:
            return other_participant.profile.name
        return None

    @strawberry_django.field(only=["image", "is_group"])
    def image(self, info: Info, width: int, height: int) -> str | None:
        from baseapp_core.strawberry.fields import build_thumbnail_url

        file = None
        if self.is_group:
            file = self.image
        elif (other := _other_participant(self, info)) and other.profile:
            file = other.profile.image
        return build_thumbnail_url(file, info, width, height)

    @connection(
        CountedConnection[ChatRoomParticipantLazyType] | None,
        filterset_class=ChatRoomParticipantFilter,
    )
    def participants(self, info: Info) -> Iterable[Model]:
        if self.is_group:
            participant = self.participants.filter(profile=_current_profile(info)).first()
            if participant:
                return self.participants.all().order_by(
                    Case(When(id=participant.id, then=0), default=1), "-role", "profile__name"
                )
        return self.participants.all()

    @connection(CountedConnection[MessageLazyType] | None, filterset_class=MessageFilter)
    def all_messages(self, info: Info) -> Iterable[Model]:
        if self.is_group:
            user = info.context.user
            if hasattr(user, "current_profile"):
                profile = user.current_profile
            else:
                profile = user.profile.pk if hasattr(user, "profile") else None
            participant = self.participants.filter(profile=profile).first()
            if participant:
                return self.messages.filter(created__gte=participant.accepted_at).order_by(
                    "-created"
                )
        return self.messages.all().order_by("-created")

    @strawberry.field(graphql_type=Optional[UnreadMessageCountLazyType])
    @django_resolver(qs_hook=None)  # async-safe in subscription payloads
    def unread_messages(self, info: Info, profile_id: strawberry.ID | None = None) -> Any:
        user = info.context.user
        if profile_id:
            profile_pk = get_pk_from_relay_id(profile_id)
            if not Profile.objects.get_if_member(pk=profile_pk, user=user):
                return None
        if not hasattr(user, "current_profile"):
            return None
        return UnreadMessageCount.objects.filter(
            room=self, profile_id=user.current_profile.pk
        ).first()

    @strawberry_django.field
    def is_archived(self, info: Info, profile_id: strawberry.ID | None = None) -> bool | None:
        if profile_id:
            profile_pk = get_pk_from_relay_id(profile_id)
            if not Profile.objects.get_if_member(pk=profile_pk, user=info.context.user):
                return None
        else:
            profile_pk = _profile_pk(info)
        return self.participants.filter(profile_id=profile_pk, has_archived_room=True).exists()

    @strawberry.field(graphql_type=Optional[ChatRoomParticipantLazyType])
    @django_resolver(qs_hook=None)
    def other_participant(self, info: Info) -> Any:
        if self.is_group:
            return None
        return _other_participant(self, info)

    @strawberry_django.field
    def is_sole_admin(self, info: Info) -> bool | None:
        if not self.is_group:
            return False
        current_profile = _current_profile(info)
        if not current_profile:
            return False
        admin = ChatRoomParticipant.ChatRoomParticipantRoles.ADMIN
        current_participant = self.participants.filter(profile_id=current_profile.pk).first()
        if not current_participant or current_participant.role != admin:
            return False
        return self.participants.filter(role=admin).count() == 1

    @strawberry_django.field
    def participant_ids(self, info: Info) -> list[strawberry.ID | None] | None:
        profiles = Profile.objects.filter(
            id__in=self.participants.values_list("profile_id", flat=True)
        )
        return [get_obj_relay_id(profile) for profile in profiles]

    @strawberry_django.field(description="Whether the given profile is a participant of this room.")
    def is_participant(self, info: Info, profile_id: strawberry.ID) -> bool | None:
        # The relay id decode can hit the database; memoize it on the request.
        cache = getattr(info.context, "_chats_relay_pk_cache", None)
        if cache is None:
            cache = info.context._chats_relay_pk_cache = {}
        if profile_id not in cache:
            cache[profile_id] = get_pk_from_relay_id(profile_id)
        profile_pk = cache[profile_id]
        if not profile_pk:
            return None
        return self.participants.filter(profile_id=profile_pk).exists()

    @classmethod
    def get_node(cls, info: Info, pk: Any) -> Model | None:
        room = ChatRoom.objects.filter(id=pk).first()
        if room is None or not info.context.user.has_perm("baseapp_chats.view_chatroom", room):
            return None
        return room
