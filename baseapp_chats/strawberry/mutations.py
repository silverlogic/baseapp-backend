import logging
from typing import Any

import strawberry
import swapper
from django.db import transaction
from django.db.models import Count, Model
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers
from strawberry import UNSET
from strawberry.file_uploads import Upload
from strawberry.types import Info

from baseapp_core.graphql import get_obj_from_relay_id, get_pk_from_relay_id
from baseapp_core.plugins import shared_services
from baseapp_core.strawberry import (
    ErrorType,
    RelayMutationInput,
    RelayMutationPayload,
    relay_mutation,
    type_for_model,
)
from baseapp_core.strawberry.connections import Edge

from ..broadcasts import edit_message as broadcast_message_edit
from ..broadcasts import room_updated
from ..utils import (
    SYSTEM_MESSAGE_GROUP_CREATED,
    SYSTEM_MESSAGE_MADE_ADMIN,
    add_profiles_to_room,
    escape_format_braces,
    read_messages,
    remove_marked_unread,
    send_chatroom_update_system_messages,
    send_message,
    send_new_chat_message_notification,
    send_system_message,
)
from .types import ChatRoomLazyType, ChatRoomParticipantLazyType, MessageLazyType

logger = logging.getLogger(__name__)

ChatRoom = swapper.load_model("baseapp_chats", "ChatRoom")
ChatRoomParticipant = swapper.load_model("baseapp_chats", "ChatRoomParticipant")
ChatRoomParticipantRoles = ChatRoomParticipant.ChatRoomParticipantRoles
Message = swapper.load_model("baseapp_chats", "Message")
UnreadMessageCount = swapper.load_model("baseapp_chats", "UnreadMessageCount")
Profile = swapper.load_model("baseapp_profiles", "Profile")
profile_app_label = Profile._meta.app_label
ProfileLazyType = type_for_model(Profile)
IDList = list[strawberry.ID | None]


class ImageSerializer(serializers.Serializer):
    image = serializers.ImageField(required=False, allow_null=True)


def _error(field: str, message: Any) -> list[ErrorType]:
    return [ErrorType(field=field, messages=[str(message)])]


def _value(value: Any) -> Any:
    """None for an omitted optional input field."""
    return None if value is UNSET else value


def _current_profile(info: Info) -> Any:
    user = info.context.user
    if hasattr(user, "current_profile"):
        return user.current_profile
    return getattr(user, "profile", None)


@strawberry.input(name="ChatRoomCreateInput")
class ChatRoomCreateInput(RelayMutationInput):
    profile_id: strawberry.ID
    participants: IDList
    is_group: bool | None = False
    title: str | None = UNSET


@strawberry.type(name="ChatRoomCreatePayload")
class ChatRoomCreatePayload(RelayMutationPayload):
    room: Edge[ChatRoomLazyType] | None = None
    profile: ProfileLazyType | None = None


@strawberry.input(name="ChatRoomUpdateInput")
class ChatRoomUpdateInput(RelayMutationInput):
    room_id: strawberry.ID
    profile_id: strawberry.ID
    title: str | None = UNSET
    image: Upload | None = UNSET
    delete_image: bool | None = False
    add_participants: IDList | None = strawberry.field(default_factory=list)
    remove_participants: IDList | None = strawberry.field(default_factory=list)


@strawberry.type(name="ChatRoomUpdatePayload")
class ChatRoomUpdatePayload(RelayMutationPayload):
    room: Edge[ChatRoomLazyType] | None = None
    removed_participants: list[ChatRoomParticipantLazyType | None] | None = None
    added_participants: list[ChatRoomParticipantLazyType | None] | None = None


@strawberry.input(name="ChatRoomsAddParticipantInput")
class ChatRoomsAddParticipantInput(RelayMutationInput):
    profile_id: strawberry.ID
    participant_profile_id: strawberry.ID
    room_ids: list[strawberry.ID]


@strawberry.type(name="ChatRoomsAddParticipantPayload")
class ChatRoomsAddParticipantPayload(RelayMutationPayload):
    rooms: list[ChatRoomLazyType | None] | None = None
    added_participants: list[ChatRoomParticipantLazyType | None] | None = None


@strawberry.input(name="ChatRoomSendMessageInput")
class ChatRoomSendMessageInput(RelayMutationInput):
    room_id: strawberry.ID
    profile_id: strawberry.ID
    content: str
    in_reply_to_id: strawberry.ID | None = UNSET
    mentioned_profile_ids: IDList | None = UNSET


@strawberry.type(name="ChatRoomSendMessagePayload")
class ChatRoomSendMessagePayload(RelayMutationPayload):
    message: Edge[MessageLazyType] | None = None


@strawberry.input(name="ChatRoomEditMessageInput")
class ChatRoomEditMessageInput(RelayMutationInput):
    id: strawberry.ID
    content: str
    mentioned_profile_ids: IDList | None = UNSET


@strawberry.type(name="ChatRoomEditMessagePayload")
class ChatRoomEditMessagePayload(RelayMutationPayload):
    message: Edge[MessageLazyType] | None = None


@strawberry.input(name="ChatRoomDeleteMessageInput")
class ChatRoomDeleteMessageInput(RelayMutationInput):
    id: strawberry.ID


@strawberry.type(name="ChatRoomDeleteMessagePayload")
class ChatRoomDeleteMessagePayload(RelayMutationPayload):
    deleted_message: Edge[MessageLazyType] | None = None


@strawberry.input(name="ChatRoomReadMessagesInput")
class ChatRoomReadMessagesInput(RelayMutationInput):
    room_id: strawberry.ID
    profile_id: strawberry.ID
    message_ids: IDList | None = UNSET


@strawberry.type(name="ChatRoomReadMessagesPayload")
class ChatRoomReadMessagesPayload(RelayMutationPayload):
    room: ChatRoomLazyType | None = None
    profile: ProfileLazyType | None = None
    messages: list[MessageLazyType | None] | None = None


@strawberry.input(name="ChatRoomUnreadInput")
class ChatRoomUnreadInput(RelayMutationInput):
    room_id: strawberry.ID
    profile_id: strawberry.ID


@strawberry.type(name="ChatRoomUnreadPayload")
class ChatRoomUnreadPayload(RelayMutationPayload):
    room: ChatRoomLazyType | None = None
    profile: ProfileLazyType | None = None


@strawberry.input(name="ChatRoomArchiveInput")
class ChatRoomArchiveInput(RelayMutationInput):
    room_id: strawberry.ID
    profile_id: strawberry.ID
    archive: bool


@strawberry.type(name="ChatRoomArchivePayload")
class ChatRoomArchivePayload(RelayMutationPayload):
    room: ChatRoomLazyType | None = None


@strawberry.input(name="ChatRoomToggleAdminInput")
class ChatRoomToggleAdminInput(RelayMutationInput):
    target_participant_id: strawberry.ID
    profile_id: strawberry.ID
    room_id: strawberry.ID


@strawberry.type(name="ChatRoomToggleAdminPayload")
class ChatRoomToggleAdminPayload(RelayMutationPayload):
    participant: Edge[ChatRoomParticipantLazyType] | None = None


# Kept verbatim (indentation included): it is the published field description.
ADD_PARTICIPANT_DESCRIPTION = """Add one profile as a MEMBER participant to multiple group chat rooms at once.

    All-or-nothing: if the acting profile can't add participants to any of the
    requested rooms, nothing is written. Rooms where the profile is already a
    participant are silently skipped (idempotent).
    """


def _resolve_rooms(info: Info, room_ids: list[str]) -> tuple[list[Model], ErrorType | None]:
    """Resolve relay ids to unique group ChatRoom instances, preserving input order."""
    rooms = []
    seen_room_pks = set()
    for room_id in room_ids:
        try:
            room = get_obj_from_relay_id(info, room_id)
        except Exception:
            room = None
        if not room or not isinstance(room, ChatRoom) or not room.is_group:
            return [], _error("room_ids", _("Some rooms are not valid"))[0]
        if room.pk in seen_room_pks:
            continue
        seen_room_pks.add(room.pk)
        rooms.append(room)
    return rooms, None


def _check_rooms_permissions(
    info: Info, profile: Model, participant_profile: Model, rooms: list[Model]
) -> ErrorType | None:
    """Return an error unless the actor can add the participant to every room."""
    for room in rooms:
        if not info.context.user.has_perm(
            "baseapp_chats.modify_chatroom",
            {"profile": profile, "room": room, "add_participants": [participant_profile.pk]},
        ):
            return _error(
                "room_ids",
                _(
                    "You don't have permission to add participants to one or "
                    "more of the selected rooms"
                ),
            )[0]
    return None


@strawberry.type
class ChatsMutations:
    @relay_mutation(login_required=True)
    def chat_room_create(
        self, info: Info, input: ChatRoomCreateInput
    ) -> ChatRoomCreatePayload | None:
        user = info.context.user
        profile = get_obj_from_relay_id(info, input.profile_id)

        if not user.has_perm(f"{profile_app_label}.use_profile", profile):
            return ChatRoomCreatePayload(
                errors=_error(
                    "profile_id", _("You don't have permission to send a message as this profile")
                )
            )

        participants = [
            get_obj_from_relay_id(info, participant) for participant in input.participants
        ]
        participants = [participant for participant in participants if participant is not None]
        participants_ids = [participant.pk for participant in participants]

        if service := shared_services.get("blocks.lookup"):
            if service.has_block_between([profile.id], participants_ids):
                return ChatRoomCreatePayload(
                    errors=_error(
                        "participants", _("You can't create a chatroom with those participants")
                    )
                )

        participants.append(profile)

        if len(participants) < 2:
            return ChatRoomCreatePayload(
                errors=_error("participants", _("You need add at least one participant"))
            )

        is_group = input.is_group or len(participants) > 2
        title = _value(input.title)
        if is_group and not title:
            return ChatRoomCreatePayload(
                errors=_error("title", _("Title is required for group chats"))
            )

        if not user.has_perm(
            "baseapp_chats.add_chatroom", {"profile": profile, "participants": participants}
        ):
            return ChatRoomCreatePayload(
                errors=_error("participants", _("You don't have permission to create a room"))
            )

        query_set = ChatRoom.objects.annotate(count=Count("participants")).filter(
            count=len(participants)
        )
        for participant in participants:
            query_set = query_set.filter(participants__profile_id=participant.id, is_group=False)
        existent_room = query_set.first()

        if existent_room and not is_group:
            return ChatRoomCreatePayload(
                profile=profile, room=Edge(node=existent_room, cursor=None)
            )

        image = info.context.FILES.get("image", None)
        serializer = ImageSerializer(data={"image": image})
        if not serializer.is_valid():
            return ChatRoomCreatePayload(
                errors=[ErrorType(field="image", messages=list(serializer.errors["image"]))]
            )

        room = ChatRoom.objects.create(
            created_by=user,
            created_by_profile=profile,
            last_message_time=timezone.now(),
            is_group=is_group,
            title=title,
            image=serializer.validated_data["image"],
        )

        created_participants = ChatRoomParticipant.objects.bulk_create(
            [
                ChatRoomParticipant(
                    profile=participant,
                    room=room,
                    role=(
                        ChatRoomParticipantRoles.ADMIN
                        if participant == profile
                        else ChatRoomParticipantRoles.MEMBER
                    ),
                    accepted_at=timezone.now(),
                )
                for participant in participants
            ]
        )

        room.participants_count = len(created_participants)
        room.save()

        if is_group:
            safe_title = escape_format_braces(title)
            send_system_message(
                room, SYSTEM_MESSAGE_GROUP_CREATED.replace("{title}", safe_title), actor=profile
            )
            room_updated(room)

        return ChatRoomCreatePayload(profile=profile, room=Edge(node=room, cursor=None))

    @relay_mutation(login_required=True)
    def chat_room_update(
        self, info: Info, input: ChatRoomUpdateInput
    ) -> ChatRoomUpdatePayload | None:
        user = info.context.user
        room_id = input.room_id
        profile_id = input.profile_id
        delete_image = input.delete_image
        add_participants = input.add_participants
        remove_participants = input.remove_participants

        room = get_obj_from_relay_id(info, room_id)
        profile = get_obj_from_relay_id(info, profile_id)
        is_sole_admin = (
            ChatRoomParticipant.objects.filter(
                profile=profile, room=room, role=ChatRoomParticipantRoles.ADMIN
            ).exists()
            and ChatRoomParticipant.objects.filter(
                room=room, role=ChatRoomParticipantRoles.ADMIN
            ).count()
            == 1
        )
        is_leaving_chatroom = profile_id in remove_participants and len(remove_participants) == 1
        add_participants_pks = [
            get_pk_from_relay_id(participant)
            for participant in add_participants
            if isinstance(participant, str)
        ]

        for participant in add_participants_pks:
            if not participant:
                return ChatRoomUpdatePayload(
                    errors=_error("add_participants", _("Some participants are not valid"))
                )

        remove_participants_pks = [
            get_pk_from_relay_id(participant) for participant in remove_participants
        ]
        participants_to_remove = ChatRoomParticipant.objects.filter(
            profile_id__in=remove_participants_pks, room=room
        )

        title = _value(input.title)
        image = info.context.FILES.get("image", None) or _value(input.image)

        if not room or not getattr(room, "is_group", False):
            return ChatRoomUpdatePayload(errors=_error("room_id", _("This room cannot be updated")))

        if not user.has_perm(f"{profile_app_label}.use_profile", profile):
            return ChatRoomUpdatePayload(
                errors=_error("profile_id", _("You don't have permission to act as this profile"))
            )

        if service := shared_services.get("blocks.lookup"):
            if service.has_block_between([profile.id], add_participants_pks):
                return ChatRoomUpdatePayload(
                    errors=_error(
                        "add_participants", _("You can't add those participants to a chatroom")
                    )
                )

        if not user.has_perm(
            "baseapp_chats.modify_chatroom",
            {
                "profile": profile,
                "room": room,
                "add_participants": add_participants_pks,
                "is_leaving_chatroom": is_leaving_chatroom,
                "modify_image": image or delete_image,
                "modify_title": title,
            },
        ):
            return ChatRoomUpdatePayload(
                errors=_error("room_id", _("You don't have permission to update this room"))
            )

        serializer = ImageSerializer(data={"image": image})
        if not serializer.is_valid():
            return ChatRoomUpdatePayload(
                errors=[ErrorType(field="image", messages=list(serializer.errors["image"]))]
            )

        # Pre-update state, for the system messages below
        previous_title = room.title
        had_image = bool(room.image)
        title_changed = title is not None and title != previous_title
        image_changed = (image is not None) or (delete_image and had_image)

        with transaction.atomic():
            removed_participants = list(participants_to_remove)
            participants_to_remove.delete()

            if is_leaving_chatroom and is_sole_admin:
                oldest_remaining_participant = (
                    ChatRoomParticipant.objects.filter(room=room).order_by("accepted_at").first()
                )
                if oldest_remaining_participant:
                    oldest_remaining_participant.role = ChatRoomParticipantRoles.ADMIN
                    oldest_remaining_participant.save(update_fields=["role"])

            created_participants = add_profiles_to_room(room, add_participants_pks)

            room.participants_count = (
                room.participants_count - len(removed_participants) + len(created_participants)
            )
            if title is not None:
                room.title = title
            if image is not None:
                room.image = serializer.validated_data["image"]
            elif delete_image:
                room.image = None
            room.save()

        room_updated(room, removed_participants, added_participants=created_participants)

        send_chatroom_update_system_messages(
            room,
            profile,
            new_title=title,
            title_changed=title_changed,
            image_changed=image_changed,
            added_participants=created_participants,
            removed_participants=removed_participants,
            is_leaving=is_leaving_chatroom,
        )

        return ChatRoomUpdatePayload(
            room=Edge(node=room, cursor=None),
            removed_participants=removed_participants,
            added_participants=created_participants,
        )

    @relay_mutation(login_required=True, description=ADD_PARTICIPANT_DESCRIPTION)
    def chat_rooms_add_participant(
        self, info: Info, input: ChatRoomsAddParticipantInput
    ) -> ChatRoomsAddParticipantPayload | None:
        profile = get_obj_from_relay_id(info, input.profile_id)

        if not info.context.user.has_perm(f"{profile_app_label}.use_profile", profile):
            return ChatRoomsAddParticipantPayload(
                errors=_error("profile_id", _("You don't have permission to act as this profile"))
            )

        try:
            participant_profile = get_obj_from_relay_id(info, input.participant_profile_id)
        except Exception:
            participant_profile = None
        if not isinstance(participant_profile, Profile):
            return ChatRoomsAddParticipantPayload(
                errors=_error("participant_profile_id", _("This profile is not valid"))
            )

        if service := shared_services.get("blocks.lookup"):
            if service.has_block_between([profile.id], [participant_profile.pk]):
                return ChatRoomsAddParticipantPayload(
                    errors=_error(
                        "participant_profile_id", _("You can't add this participant to a chatroom")
                    )
                )

        # Resolve every room before any write (all-or-nothing)
        rooms, resolve_error = _resolve_rooms(info, input.room_ids)
        if resolve_error:
            return ChatRoomsAddParticipantPayload(errors=[resolve_error])

        if not rooms:
            return ChatRoomsAddParticipantPayload(
                errors=_error("room_ids", _("You need to select at least one room"))
            )

        added_participants = []
        rooms_with_new_participant = []
        with transaction.atomic():
            # Lock rooms in pk order so concurrent adds stay idempotent and counts lossless
            locked_rooms_by_pk = {
                locked_room.pk: locked_room
                for locked_room in ChatRoom.objects.select_for_update()
                .filter(pk__in=[room.pk for room in rooms])
                .order_by("pk")
            }
            if len(locked_rooms_by_pk) != len(rooms):
                return ChatRoomsAddParticipantPayload(
                    errors=_error("room_ids", _("Some rooms are not valid"))
                )
            rooms = [locked_rooms_by_pk[room.pk] for room in rooms]

            # Check permissions under the lock, before any write
            permission_error = _check_rooms_permissions(info, profile, participant_profile, rooms)
            if permission_error:
                return ChatRoomsAddParticipantPayload(errors=[permission_error])

            for room in rooms:
                created_participants = add_profiles_to_room(room, [participant_profile.pk])
                if created_participants:
                    room.participants_count = room.participants_count + len(created_participants)
                    room.save(update_fields=["participants_count"])
                    added_participants.extend(created_participants)
                    rooms_with_new_participant.append((room, created_participants))

        for room, created_participants in rooms_with_new_participant:
            # Memberships are committed: notification failures must not fail the mutation
            try:
                room_updated(room, added_participants=created_participants)
                send_chatroom_update_system_messages(
                    room, profile, added_participants=created_participants
                )
            except Exception:
                logger.exception(
                    "Failed to send chat room update notifications for room %s", room.pk
                )

        return ChatRoomsAddParticipantPayload(rooms=rooms, added_participants=added_participants)

    @relay_mutation(login_required=True)
    def chat_room_send_message(
        self, info: Info, input: ChatRoomSendMessageInput
    ) -> ChatRoomSendMessagePayload | None:
        user = info.context.user
        content = input.content
        room = get_obj_from_relay_id(info, input.room_id)
        profile = get_obj_from_relay_id(info, input.profile_id)

        in_reply_to = None
        if in_reply_to_id := _value(input.in_reply_to_id):
            in_reply_to = Message.objects.filter(
                pk=get_pk_from_relay_id(in_reply_to_id), room=room
            ).first()

        if not user.has_perm(f"{profile_app_label}.use_profile", profile):
            return ChatRoomSendMessagePayload(
                errors=_error(
                    "profile_id", _("You don't have permission to send a message as this profile")
                )
            )

        if not room or not user.has_perm(
            "baseapp_chats.add_message", {"profile": profile, "room": room}
        ):
            return ChatRoomSendMessagePayload(
                errors=_error(
                    "room_id", _("You don't have permission to send a message in this room")
                )
            )

        if len(content) < 1:
            return ChatRoomSendMessagePayload(
                errors=_error("content", _("You need to write something"))
            )

        if len(content) > 1000:
            return ChatRoomSendMessagePayload(
                errors=_error("content", _("You can't write more than 1000 characters"))
            )

        message = send_message(
            profile=profile,
            user=user,
            content=content,
            room=room,
            verb=Message.Verbs.SENT_MESSAGE,
            room_id=input.room_id,
            in_reply_to=in_reply_to,
        )

        if mentioned_profile_ids := _value(input.mentioned_profile_ids) or []:
            if service := shared_services.get("mentions"):
                service.update_mentions(message, mentioned_profile_ids, exclude_profile=profile)

        send_new_chat_message_notification(room, message, info)
        read_messages(room, profile)

        return ChatRoomSendMessagePayload(message=Edge(node=message, cursor=None))

    @relay_mutation(login_required=True)
    def chat_room_edit_message(
        self, info: Info, input: ChatRoomEditMessageInput
    ) -> ChatRoomEditMessagePayload | None:
        mentioned_profile_ids = _value(input.mentioned_profile_ids)
        try:
            message = Message.objects.get(pk=get_pk_from_relay_id(input.id))
        except Message.DoesNotExist:
            return ChatRoomEditMessagePayload(errors=_error("id", _("Message does not exist")))

        profile = _current_profile(info)
        if not info.context.user.has_perm(
            "baseapp_chats.change_message", {"profile": profile, "message": message}
        ):
            return ChatRoomEditMessagePayload(
                errors=_error("id", _("You don't have permission to update this message"))
            )

        content = input.content
        if len(content) < 1:
            return ChatRoomEditMessagePayload(
                errors=_error("content", _("You cannot edit an empty message"))
            )

        if len(content) > 1000:
            return ChatRoomEditMessagePayload(
                errors=_error("content", _("Message must be no longer than 1000 characters"))
            )

        message.content = content
        message.save(update_fields=["content"])

        if mentioned_profile_ids is not None:
            if service := shared_services.get("mentions"):
                service.update_mentions(message, mentioned_profile_ids, exclude_profile=profile)

        broadcast_message_edit(message, room_id=message.room.relay_id)

        return ChatRoomEditMessagePayload(message=Edge(node=message, cursor=None))

    @relay_mutation(login_required=True)
    def chat_room_delete_message(
        self, info: Info, input: ChatRoomDeleteMessageInput
    ) -> ChatRoomDeleteMessagePayload | None:
        try:
            message = Message.objects.get(pk=get_pk_from_relay_id(input.id))
        except Message.DoesNotExist:
            return ChatRoomDeleteMessagePayload(errors=_error("id", _("Message does not exist")))

        if message.deleted:
            return ChatRoomDeleteMessagePayload(
                errors=_error("deleted", _("This message has already been deleted"))
            )

        profile = _current_profile(info)
        if not info.context.user.has_perm(
            "baseapp_chats.delete_message", {"profile": profile, "message": message}
        ):
            return ChatRoomDeleteMessagePayload(
                errors=_error("id", _("You don't have permission to update this message"))
            )

        message.deleted = True
        message.save(update_fields=["deleted"])

        broadcast_message_edit(message, room_id=message.room.relay_id)

        return ChatRoomDeleteMessagePayload(deleted_message=Edge(node=message, cursor=None))

    @relay_mutation(login_required=True)
    def chat_room_read_messages(
        self, info: Info, input: ChatRoomReadMessagesInput
    ) -> ChatRoomReadMessagesPayload | None:
        room = get_obj_from_relay_id(info, input.room_id)
        profile = get_obj_from_relay_id(info, input.profile_id)

        if not info.context.user.has_perm(f"{profile_app_label}.use_profile", profile):
            return ChatRoomReadMessagesPayload(
                errors=_error("profile_id", _("You don't have permission to act as this profile"))
            )

        if not ChatRoomParticipant.objects.filter(profile_id=profile.pk, room=room).exists():
            return ChatRoomReadMessagesPayload(
                errors=_error("participant", _("Participant is not part of the room."))
            )

        remove_marked_unread(room, profile)
        messages = read_messages(room, profile, _value(input.message_ids))
        return ChatRoomReadMessagesPayload(room=room, profile=profile, messages=messages)

    @relay_mutation(login_required=True)
    def chat_room_unread(
        self, info: Info, input: ChatRoomUnreadInput
    ) -> ChatRoomUnreadPayload | None:
        room = get_obj_from_relay_id(info, input.room_id)
        profile = get_obj_from_relay_id(info, input.profile_id)

        if not info.context.user.has_perm(f"{profile_app_label}.use_profile", profile):
            return ChatRoomUnreadPayload(
                errors=_error("profile_id", _("You don't have permission to act as this profile"))
            )

        if not ChatRoomParticipant.objects.filter(profile_id=profile.pk, room=room).exists():
            return ChatRoomUnreadPayload(
                errors=_error("participant", _("Participant is not part of the room."))
            )

        UnreadMessageCount.objects.update_or_create(
            profile=profile, room=room, defaults={"marked_unread": True}
        )

        return ChatRoomUnreadPayload(room=room, profile=profile)

    @relay_mutation(login_required=True)
    def chat_room_archive(
        self, info: Info, input: ChatRoomArchiveInput
    ) -> ChatRoomArchivePayload | None:
        room = get_obj_from_relay_id(info, input.room_id)
        profile = get_obj_from_relay_id(info, input.profile_id)

        if not info.context.user.has_perm(f"{profile_app_label}.use_profile", profile):
            return ChatRoomArchivePayload(
                errors=_error(
                    "profile_id",
                    _("You don't have permission to archive this chatroom as this profile"),
                )
            )

        participant = ChatRoomParticipant.objects.filter(profile_id=profile.pk, room=room).first()
        if not participant:
            return ChatRoomArchivePayload(
                errors=_error("participant", _("Participant is not part of the room."))
            )

        with transaction.atomic():
            participant = ChatRoomParticipant.objects.select_for_update().get(pk=participant.pk)
            participant.has_archived_room = input.archive
            participant.save()
            room.refresh_from_db()
        return ChatRoomArchivePayload(room=room)

    @relay_mutation(login_required=True)
    def chat_room_toggle_admin(
        self, info: Info, input: ChatRoomToggleAdminInput
    ) -> ChatRoomToggleAdminPayload | None:
        room = get_obj_from_relay_id(info, input.room_id)
        profile = get_obj_from_relay_id(info, input.profile_id)

        if not info.context.user.has_perm(f"{profile_app_label}.use_profile", profile):
            return ChatRoomToggleAdminPayload(
                errors=_error("profile_id", _("You don't have permission to use this profile"))
            )

        if not info.context.user.has_perm(
            "baseapp_chats.modify_chatroom", {"profile": profile, "room": room}
        ):
            return ChatRoomToggleAdminPayload(
                errors=_error("room_id", _("You don't have permission to update this room"))
            )

        target_participant = ChatRoomParticipant.objects.filter(
            pk=get_pk_from_relay_id(input.target_participant_id), room=room
        ).first()
        if not target_participant:
            return ChatRoomToggleAdminPayload(
                errors=_error(
                    "target_participant_id", _("The target participant is not part of the room")
                )
            )

        participant_is_admin = target_participant.role == ChatRoomParticipantRoles.ADMIN

        with transaction.atomic():
            if not participant_is_admin:
                target_participant.role = ChatRoomParticipantRoles.ADMIN
                target_participant.save(update_fields=["role"])
            else:
                # Keep at least one admin, concurrent-safe
                admin_count = (
                    ChatRoomParticipant.objects.select_for_update()
                    .filter(room=room, role=ChatRoomParticipantRoles.ADMIN)
                    .count()
                )
                # TODO: Define if user can remove their own admin role
                if admin_count <= 1:
                    return ChatRoomToggleAdminPayload(
                        errors=_error(
                            "target_participant_id", _("The room must have at least one admin")
                        )
                    )
                target_participant.role = ChatRoomParticipantRoles.MEMBER
                target_participant.save(update_fields=["role"])

        if not participant_is_admin:
            send_system_message(
                room, SYSTEM_MESSAGE_MADE_ADMIN, actor=profile, target=target_participant.profile
            )

        return ChatRoomToggleAdminPayload(participant=Edge(node=target_participant, cursor=None))
