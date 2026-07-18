import logging

import graphene
import swapper
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Count, Model
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from graphene_django.types import ErrorType
from graphene_file_upload.scalars import Upload
from rest_framework import serializers

from baseapp_chats.graphql.subscriptions import (
    ChatRoomOnMessage,
    ChatRoomOnMessagesCountUpdate,
    ChatRoomOnRoomUpdate,
)
from baseapp_chats.utils import (
    SYSTEM_MESSAGE_GROUP_CREATED,
    SYSTEM_MESSAGE_MADE_ADMIN,
    add_profiles_to_room,
    escape_format_braces,
    send_chatroom_update_system_messages,
    send_message,
    send_new_chat_message_notification,
    send_system_message,
)
from baseapp_core.graphql import (
    RelayMutation,
    get_obj_from_relay_id,
    get_pk_from_relay_id,
    login_required,
)
from baseapp_core.plugins import shared_services

logger = logging.getLogger(__name__)

ChatRoom = swapper.load_model("baseapp_chats", "ChatRoom")
ChatRoomParticipant = swapper.load_model("baseapp_chats", "ChatRoomParticipant")
ChatRoomParticipantRoles = ChatRoomParticipant.ChatRoomParticipantRoles
Message = swapper.load_model("baseapp_chats", "Message")
MessageStatus = swapper.load_model("baseapp_chats", "MessageStatus")
UnreadMessageCount = swapper.load_model("baseapp_chats", "UnreadMessageCount")
User = get_user_model()
Profile = swapper.load_model("baseapp_profiles", "Profile")
profile_app_label = Profile._meta.app_label


ChatRoomObjectType = ChatRoom.get_graphql_object_type()
ProfileObjectType = Profile.get_graphql_object_type()
MessageObjectType = Message.get_graphql_object_type()
ChatRoomParticipantObjectType = ChatRoomParticipant.get_graphql_object_type()


class ImageSerializer(serializers.Serializer):
    image = serializers.ImageField(required=False, allow_null=True)


class ChatRoomCreate(RelayMutation):
    room = graphene.Field(ChatRoomObjectType._meta.connection.Edge)
    profile = graphene.Field(ProfileObjectType)

    class Input:
        profile_id = graphene.ID(required=True)
        participants = graphene.List(graphene.ID, required=True)
        is_group = graphene.Boolean(required=False, default_value=False)
        title = graphene.String(required=False)

    @classmethod
    @login_required
    def mutate_and_get_payload(
        cls, root, info, profile_id, participants, is_group, **input
    ) -> "ChatRoomCreate":
        profile = get_obj_from_relay_id(info, profile_id)

        if not info.context.user.has_perm(f"{profile_app_label}.use_profile", profile):
            return ChatRoomCreate(
                errors=[
                    ErrorType(
                        field="profile_id",
                        messages=[_("You don't have permission to send a message as this profile")],
                    )
                ]
            )

        participants = [get_obj_from_relay_id(info, participant) for participant in participants]
        participants = [participant for participant in participants if participant is not None]
        participants_ids = [participant.pk for participant in participants]

        # Check if participants are blocked
        if service := shared_services.get("blocks.lookup"):
            if service.has_block_between([profile.id], participants_ids):
                return ChatRoomCreate(
                    errors=[
                        ErrorType(
                            field="participants",
                            messages=[_("You can't create a chatroom with those participants")],
                        )
                    ]
                )

        participants.append(profile)

        if len(participants) < 2:
            return ChatRoomCreate(
                errors=[
                    ErrorType(
                        field="participants",
                        messages=[_("You need add at least one participant")],
                    )
                ]
            )

        is_group = is_group or len(participants) > 2
        title = input.get("title", None)
        if is_group and not title:
            return ChatRoomCreate(
                errors=[
                    ErrorType(
                        field="title",
                        messages=[_("Title is required for group chats")],
                    )
                ]
            )

        if not info.context.user.has_perm(
            "baseapp_chats.add_chatroom", {"profile": profile, "participants": participants}
        ):
            return ChatRoomCreate(
                errors=[
                    ErrorType(
                        field="participants",
                        messages=[_("You don't have permission to create a room")],
                    )
                ]
            )

        query_set = ChatRoom.objects.annotate(count=Count("participants")).filter(
            count=len(participants)
        )
        for participant in participants:
            query_set = query_set.filter(
                participants__profile_id=participant.id,
                is_group=False,
            )
        existent_room = query_set.first()

        if existent_room and not is_group:
            return ChatRoomCreate(
                profile=profile,
                room=ChatRoomObjectType._meta.connection.Edge(
                    node=existent_room,
                ),
            )
        image = info.context.FILES.get("image", None)
        serializer = ImageSerializer(data={"image": image})
        if not serializer.is_valid():
            return ChatRoomCreate(
                errors=[ErrorType(field="image", messages=serializer.errors["image"])]
            )

        room = ChatRoom.objects.create(
            created_by=info.context.user,
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
                room,
                SYSTEM_MESSAGE_GROUP_CREATED.replace("{title}", safe_title),
                actor=profile,
            )
            ChatRoomOnRoomUpdate.room_updated(room)

        return ChatRoomCreate(
            profile=profile,
            room=ChatRoomObjectType._meta.connection.Edge(
                node=room,
            ),
        )


class ChatRoomUpdate(RelayMutation):
    room = graphene.Field(ChatRoomObjectType._meta.connection.Edge)
    removed_participants = graphene.List(ChatRoomParticipantObjectType)
    added_participants = graphene.List(ChatRoomParticipantObjectType)

    class Input:
        room_id = graphene.ID(required=True)
        profile_id = graphene.ID(required=True)
        title = graphene.String(required=False)
        image = Upload(required=False)
        delete_image = graphene.Boolean(default_value=False)
        add_participants = graphene.List(graphene.ID, default_value=[])
        remove_participants = graphene.List(graphene.ID, default_value=[])

    @classmethod
    @login_required
    def mutate_and_get_payload(
        cls,
        root,
        info,
        room_id,
        profile_id,
        delete_image,
        add_participants,
        remove_participants,
        **input,
    ) -> "ChatRoomUpdate":
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

        # if relay id is not valid return error
        for participant in add_participants_pks:
            if not participant:
                return ChatRoomUpdate(
                    errors=[
                        ErrorType(
                            field="add_participants",
                            messages=[_("Some participants are not valid")],
                        )
                    ]
                )

        remove_participants_pks = [
            get_pk_from_relay_id(participant) for participant in remove_participants
        ]
        participants_to_remove = ChatRoomParticipant.objects.filter(
            profile_id__in=remove_participants_pks, room=room
        )

        title = input.get("title", None)
        image = info.context.FILES.get("image", None) or input.get("image", None)

        if not room or not getattr(room, "is_group", False):
            return ChatRoomUpdate(
                errors=[
                    ErrorType(
                        field="room_id",
                        messages=[_("This room cannot be updated")],
                    )
                ]
            )

        if not info.context.user.has_perm(f"{profile_app_label}.use_profile", profile):
            return ChatRoomUpdate(
                errors=[
                    ErrorType(
                        field="profile_id",
                        messages=[_("You don't have permission to act as this profile")],
                    )
                ]
            )

        # Check if added participants are blocked
        if service := shared_services.get("blocks.lookup"):
            if service.has_block_between([profile.id], add_participants_pks):
                return ChatRoomUpdate(
                    errors=[
                        ErrorType(
                            field="add_participants",
                            messages=[_("You can't add those participants to a chatroom")],
                        )
                    ]
                )

        if not info.context.user.has_perm(
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
            return ChatRoomUpdate(
                errors=[
                    ErrorType(
                        field="room_id",
                        messages=[_("You don't have permission to update this room")],
                    )
                ]
            )

        # Change image
        serializer = ImageSerializer(data={"image": image})
        if not serializer.is_valid():
            return ChatRoomUpdate(
                errors=[ErrorType(field="image", messages=serializer.errors["image"])]
            )

        # Capture pre-update state so we can emit accurate system messages below
        previous_title = room.title
        had_image = bool(room.image)
        title_changed = title is not None and title != previous_title
        image_changed = (image is not None) or (delete_image and had_image)

        with transaction.atomic():
            # Removing participants
            removed_participants = list(participants_to_remove)
            participants_to_remove.delete()

            # Setting new admin if needed
            if is_leaving_chatroom and is_sole_admin:
                oldest_remaining_participant = (
                    ChatRoomParticipant.objects.filter(room=room).order_by("accepted_at").first()
                )
                if oldest_remaining_participant:
                    oldest_remaining_participant.role = ChatRoomParticipantRoles.ADMIN
                    oldest_remaining_participant.save(update_fields=["role"])

            # Adding new participants
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

        ChatRoomOnRoomUpdate.room_updated(
            room, removed_participants, added_participants=created_participants
        )

        # Emit the system messages describing what changed in the group
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

        return ChatRoomUpdate(
            room=ChatRoomObjectType._meta.connection.Edge(
                node=room,
            ),
            removed_participants=removed_participants,
            added_participants=created_participants,
        )


class ChatRoomsAddParticipant(RelayMutation):
    """Add one profile as a MEMBER participant to multiple group chat rooms at once.

    All-or-nothing: if the acting profile can't add participants to any of the
    requested rooms, nothing is written. Rooms where the profile is already a
    participant are silently skipped (idempotent).
    """

    rooms = graphene.List(
        ChatRoomObjectType,
        description="All requested rooms, after the update.",
    )
    added_participants = graphene.List(
        ChatRoomParticipantObjectType,
        description="Participant rows actually created (already-member rooms are skipped).",
    )

    class Input:
        profile_id = graphene.ID(
            required=True, description="Relay id of the acting profile (must be manageable)."
        )
        participant_profile_id = graphene.ID(
            required=True, description="Relay id of the profile to add to the rooms."
        )
        room_ids = graphene.List(
            graphene.NonNull(graphene.ID),
            required=True,
            description="Relay ids of the group rooms to add the participant to.",
        )

    @classmethod
    def _resolve_rooms(
        cls, info: graphene.ResolveInfo, room_ids: list[str]
    ) -> tuple[list[Model], ErrorType | None]:
        """Resolve relay ids to unique group ChatRoom instances, preserving input order."""
        rooms = []
        seen_room_pks = set()
        for room_id in room_ids:
            try:
                room = get_obj_from_relay_id(info, room_id)
            except Exception:
                room = None
            if not room or not isinstance(room, ChatRoom) or not room.is_group:
                return [], ErrorType(
                    field="room_ids",
                    messages=[_("Some rooms are not valid")],
                )

            if room.pk in seen_room_pks:
                continue
            seen_room_pks.add(room.pk)
            rooms.append(room)

        return rooms, None

    @classmethod
    def _check_rooms_permissions(
        cls,
        info: graphene.ResolveInfo,
        profile: Model,
        participant_profile: Model,
        rooms: list[Model],
    ) -> ErrorType | None:
        """Return an error unless the actor can add the participant to every room."""
        for room in rooms:
            if not info.context.user.has_perm(
                "baseapp_chats.modify_chatroom",
                {
                    "profile": profile,
                    "room": room,
                    "add_participants": [participant_profile.pk],
                },
            ):
                return ErrorType(
                    field="room_ids",
                    messages=[
                        _(
                            "You don't have permission to add participants to one or "
                            "more of the selected rooms"
                        )
                    ],
                )
        return None

    @classmethod
    @login_required
    def mutate_and_get_payload(
        cls,
        root,
        info: graphene.ResolveInfo,
        profile_id: str,
        participant_profile_id: str,
        room_ids: list[str],
        **input,
    ) -> "ChatRoomsAddParticipant":
        profile = get_obj_from_relay_id(info, profile_id)

        if not info.context.user.has_perm(f"{profile_app_label}.use_profile", profile):
            return ChatRoomsAddParticipant(
                errors=[
                    ErrorType(
                        field="profile_id",
                        messages=[_("You don't have permission to act as this profile")],
                    )
                ]
            )

        try:
            participant_profile = get_obj_from_relay_id(info, participant_profile_id)
        except Exception:
            participant_profile = None
        if not isinstance(participant_profile, Profile):
            return ChatRoomsAddParticipant(
                errors=[
                    ErrorType(
                        field="participant_profile_id",
                        messages=[_("This profile is not valid")],
                    )
                ]
            )

        # Check if the participant is blocked
        if service := shared_services.get("blocks.lookup"):
            if service.has_block_between([profile.id], [participant_profile.pk]):
                return ChatRoomsAddParticipant(
                    errors=[
                        ErrorType(
                            field="participant_profile_id",
                            messages=[_("You can't add this participant to a chatroom")],
                        )
                    ]
                )

        # Resolve every room before any write (all-or-nothing)
        rooms, resolve_error = cls._resolve_rooms(info, room_ids)
        if resolve_error:
            return ChatRoomsAddParticipant(errors=[resolve_error])

        if not rooms:
            return ChatRoomsAddParticipant(
                errors=[
                    ErrorType(
                        field="room_ids",
                        messages=[_("You need to select at least one room")],
                    )
                ]
            )

        added_participants = []
        rooms_with_new_participant = []
        with transaction.atomic():
            # Lock the room rows in deterministic pk order to serialize concurrent
            # participant adds (keeps add_profiles_to_room idempotent and the
            # participants_count increments lossless under concurrency)
            locked_rooms_by_pk = {
                locked_room.pk: locked_room
                for locked_room in ChatRoom.objects.select_for_update()
                .filter(pk__in=[room.pk for room in rooms])
                .order_by("pk")
            }
            if len(locked_rooms_by_pk) != len(rooms):
                return ChatRoomsAddParticipant(
                    errors=[
                        ErrorType(
                            field="room_ids",
                            messages=[_("Some rooms are not valid")],
                        )
                    ]
                )
            rooms = [locked_rooms_by_pk[room.pk] for room in rooms]

            # Validate permissions under the lock, before any write, so a
            # concurrent demotion/removal committed after resolving the rooms
            # is still taken into account (all-or-nothing)
            permission_error = cls._check_rooms_permissions(
                info, profile, participant_profile, rooms
            )
            if permission_error:
                return ChatRoomsAddParticipant(errors=[permission_error])

            for room in rooms:
                created_participants = add_profiles_to_room(room, [participant_profile.pk])
                if created_participants:
                    room.participants_count = room.participants_count + len(created_participants)
                    room.save(update_fields=["participants_count"])
                    added_participants.extend(created_participants)
                    rooms_with_new_participant.append((room, created_participants))

        for room, created_participants in rooms_with_new_participant:
            # Memberships are already committed: notification failures must not
            # surface as mutation errors nor block the remaining rooms
            try:
                ChatRoomOnRoomUpdate.room_updated(room, added_participants=created_participants)
                send_chatroom_update_system_messages(
                    room, profile, added_participants=created_participants
                )
            except Exception:
                logger.exception(
                    "Failed to send chat room update notifications for room %s", room.pk
                )

        return ChatRoomsAddParticipant(
            rooms=rooms,
            added_participants=added_participants,
        )


class ChatRoomToggleAdmin(RelayMutation):
    participant = graphene.Field(ChatRoomParticipantObjectType._meta.connection.Edge)

    class Input:
        target_participant_id = graphene.ID(required=True)
        profile_id = graphene.ID(required=True)
        room_id = graphene.ID(required=True)

    @classmethod
    @login_required
    def mutate_and_get_payload(
        cls,
        root,
        info,
        target_participant_id,
        profile_id,
        room_id,
    ) -> "ChatRoomToggleAdmin":
        room = get_obj_from_relay_id(info, room_id)
        profile = get_obj_from_relay_id(info, profile_id)

        if not info.context.user.has_perm(f"{profile_app_label}.use_profile", profile):
            return ChatRoomToggleAdmin(
                errors=[
                    ErrorType(
                        field="profile_id",
                        messages=[_("You don't have permission to use this profile")],
                    )
                ]
            )

        if not info.context.user.has_perm(
            "baseapp_chats.modify_chatroom",
            {
                "profile": profile,
                "room": room,
            },
        ):
            return ChatRoomToggleAdmin(
                errors=[
                    ErrorType(
                        field="room_id",
                        messages=[_("You don't have permission to update this room")],
                    )
                ]
            )

        target_participant_pk = get_pk_from_relay_id(target_participant_id)

        target_participant = ChatRoomParticipant.objects.filter(
            pk=target_participant_pk,
            room=room,
        ).first()
        if not target_participant:
            return ChatRoomToggleAdmin(
                errors=[
                    ErrorType(
                        field="target_participant_id",
                        messages=[_("The target participant is not part of the room")],
                    )
                ]
            )

        participant_is_admin = target_participant.role == ChatRoomParticipantRoles.ADMIN

        with transaction.atomic():
            if not participant_is_admin:
                target_participant.role = ChatRoomParticipantRoles.ADMIN
                target_participant.save(update_fields=["role"])
            elif participant_is_admin:
                # Ensure at least one admin remains, in a concurrent-safe way
                admin_count = (
                    ChatRoomParticipant.objects.select_for_update()
                    .filter(room=room, role=ChatRoomParticipantRoles.ADMIN)
                    .count()
                )
                # TODO: Define if user can remove their own admin role
                if admin_count <= 1:
                    return ChatRoomToggleAdmin(
                        errors=[
                            ErrorType(
                                field="target_participant_id",
                                messages=[_("The room must have at least one admin")],
                            )
                        ]
                    )
                target_participant.role = ChatRoomParticipantRoles.MEMBER
                target_participant.save(update_fields=["role"])

        if not participant_is_admin:
            send_system_message(
                room,
                SYSTEM_MESSAGE_MADE_ADMIN,
                actor=profile,
                target=target_participant.profile,
            )

        return ChatRoomToggleAdmin(
            participant=ChatRoomParticipantObjectType._meta.connection.Edge(
                node=target_participant,
            ),
        )


class ChatRoomSendMessage(RelayMutation):
    message = graphene.Field(MessageObjectType._meta.connection.Edge)

    class Input:
        room_id = graphene.ID(required=True)
        profile_id = graphene.ID(required=True)
        content = graphene.String(required=True)
        in_reply_to_id = graphene.ID(required=False)
        mentioned_profile_ids = graphene.List(graphene.ID, required=False)

    @classmethod
    @login_required
    def mutate_and_get_payload(
        cls, root, info, room_id, content, profile_id, in_reply_to_id=None, **input
    ) -> "ChatRoomSendMessage":
        room = get_obj_from_relay_id(info, room_id)
        profile = get_obj_from_relay_id(info, profile_id)

        in_reply_to = None
        if in_reply_to_id:
            in_reply_to_pk = get_pk_from_relay_id(in_reply_to_id)
            in_reply_to = Message.objects.filter(
                pk=in_reply_to_pk,
                room=room,
            ).first()

        if not info.context.user.has_perm(f"{profile_app_label}.use_profile", profile):
            return ChatRoomSendMessage(
                errors=[
                    ErrorType(
                        field="profile_id",
                        messages=[_("You don't have permission to send a message as this profile")],
                    )
                ]
            )

        if not room or not info.context.user.has_perm(
            "baseapp_chats.add_message", {"profile": profile, "room": room}
        ):
            return ChatRoomSendMessage(
                errors=[
                    ErrorType(
                        field="room_id",
                        messages=[_("You don't have permission to send a message in this room")],
                    )
                ]
            )

        if len(content) < 1:
            return ChatRoomSendMessage(
                errors=[
                    ErrorType(
                        field="content",
                        messages=[_("You need to write something")],
                    )
                ]
            )

        if len(content) > 1000:
            return ChatRoomSendMessage(
                errors=[
                    ErrorType(
                        field="content",
                        messages=[_("You can't write more than 1000 characters")],
                    )
                ]
            )

        message = send_message(
            profile=profile,
            user=info.context.user,
            content=content,
            room=room,
            verb=Message.Verbs.SENT_MESSAGE,
            room_id=room_id,
            in_reply_to=in_reply_to,
        )

        mentioned_profile_ids = input.pop("mentioned_profile_ids", None) or []
        if mentioned_profile_ids:
            if service := shared_services.get("mentions"):
                service.update_mentions(
                    message,
                    mentioned_profile_ids,
                    exclude_profile=profile,
                )

        send_new_chat_message_notification(room, message, info)
        ChatRoomReadMessages.read_messages(room, profile)

        return ChatRoomSendMessage(
            message=MessageObjectType._meta.connection.Edge(
                node=message,
            )
        )


class ChatRoomEditMessage(RelayMutation):
    message = graphene.Field(MessageObjectType._meta.connection.Edge)

    class Input:
        id = graphene.ID(required=True)
        content = graphene.String(required=True)
        mentioned_profile_ids = graphene.List(graphene.ID, required=False)

    @classmethod
    @login_required
    def mutate_and_get_payload(cls, root, info, **input) -> "ChatRoomEditMessage":
        mentioned_profile_ids = input.pop("mentioned_profile_ids", None)
        pk = get_pk_from_relay_id(input.get("id"))
        try:
            message = Message.objects.get(pk=pk)
        except Message.DoesNotExist:
            return ChatRoomEditMessage(
                errors=[
                    ErrorType(
                        field="id",
                        messages=[_("Message does not exist")],
                    )
                ]
            )

        profile = (
            info.context.user.current_profile
            if hasattr(info.context.user, "current_profile")
            else (info.context.user.profile if hasattr(info.context.user, "profile") else None)
        )
        if not info.context.user.has_perm(
            "baseapp_chats.change_message",
            {
                "profile": profile,
                "message": message,
            },
        ):
            return ChatRoomEditMessage(
                errors=[
                    ErrorType(
                        field="id",
                        messages=[_("You don't have permission to update this message")],
                    )
                ]
            )

        content = input.get("content")
        if len(content) < 1:
            return ChatRoomEditMessage(
                errors=[
                    ErrorType(
                        field="content",
                        messages=[_("You cannot edit an empty message")],
                    )
                ]
            )

        if len(content) > 1000:
            return ChatRoomEditMessage(
                errors=[
                    ErrorType(
                        field="content",
                        messages=[_("Message must be no longer than 1000 characters")],
                    )
                ]
            )

        message.content = content
        message.save(update_fields=["content"])

        if mentioned_profile_ids is not None:
            if service := shared_services.get("mentions"):
                service.update_mentions(
                    message,
                    mentioned_profile_ids,
                    exclude_profile=profile,
                )

        ChatRoomOnMessage.edit_message(room_id=message.room.relay_id, message=message)

        return ChatRoomEditMessage(
            message=MessageObjectType._meta.connection.Edge(
                node=message,
            )
        )


class ChatRoomDeleteMessage(RelayMutation):
    deleted_message = graphene.Field(MessageObjectType._meta.connection.Edge)

    class Input:
        id = graphene.ID(required=True)

    @classmethod
    @login_required
    def mutate_and_get_payload(cls, root, info, **input) -> "ChatRoomDeleteMessage":
        pk = get_pk_from_relay_id(input.get("id"))
        try:
            message = Message.objects.get(pk=pk)
        except Message.DoesNotExist:
            return ChatRoomDeleteMessage(
                errors=[
                    ErrorType(
                        field="id",
                        messages=[_("Message does not exist")],
                    )
                ]
            )

        if message.deleted:
            return ChatRoomDeleteMessage(
                errors=[
                    ErrorType(
                        field="deleted",
                        messages=[_("This message has already been deleted")],
                    )
                ]
            )

        profile = (
            info.context.user.current_profile
            if hasattr(info.context.user, "current_profile")
            else (info.context.user.profile if hasattr(info.context.user, "profile") else None)
        )

        if not info.context.user.has_perm(
            "baseapp_chats.delete_message",
            {
                "profile": profile,
                "message": message,
            },
        ):
            return ChatRoomDeleteMessage(
                errors=[
                    ErrorType(
                        field="id",
                        messages=[_("You don't have permission to update this message")],
                    )
                ]
            )

        message.deleted = True
        message.save(update_fields=["deleted"])

        ChatRoomOnMessage.edit_message(room_id=message.room.relay_id, message=message)

        return ChatRoomDeleteMessage(
            deleted_message=MessageObjectType._meta.connection.Edge(
                node=message,
            )
        )


class ChatRoomReadMessages(RelayMutation):
    room = graphene.Field(ChatRoomObjectType)
    profile = graphene.Field(ProfileObjectType)
    messages = graphene.List(MessageObjectType)

    class Input:
        room_id = graphene.ID(required=True)
        profile_id = graphene.ID(required=True)
        message_ids = graphene.List(graphene.ID, required=False)

    @classmethod
    @login_required
    def mutate_and_get_payload(
        cls, root, info, room_id, profile_id, message_ids=None, **input
    ) -> "ChatRoomReadMessages":
        room = get_obj_from_relay_id(info, room_id)
        profile = get_obj_from_relay_id(info, profile_id)

        if not info.context.user.has_perm(f"{profile_app_label}.use_profile", profile):
            return ChatRoomReadMessages(
                errors=[
                    ErrorType(
                        field="profile_id",
                        messages=[_("You don't have permission to act as this profile")],
                    )
                ]
            )

        if not ChatRoomParticipant.objects.filter(
            profile_id=profile.pk,
            room=room,
        ).exists():
            return ChatRoomReadMessages(
                errors=[
                    ErrorType(
                        field="participant",
                        messages=[_("Participant is not part of the room.")],
                    )
                ]
            )

        cls.remove_marked_unread(room, profile)
        return cls.read_messages(room, profile, message_ids)

    @classmethod
    def remove_marked_unread(cls, room, profile) -> None:
        UnreadMessageCount.objects.filter(profile=profile, room=room, marked_unread=True).update(
            marked_unread=False
        )

    @classmethod
    def read_messages(cls, room, profile, message_ids=None) -> "ChatRoomReadMessages":
        messages_status_qs = MessageStatus.objects.filter(
            profile_id=profile.pk,
            is_read=False,
        )

        if message_ids:
            message_ids = [get_pk_from_relay_id(message_id) for message_id in message_ids]
            messages_status_qs = messages_status_qs.filter(
                message_id__in=message_ids,
            )
        else:
            messages_status_qs = messages_status_qs.filter(
                message__room_id=room.pk,
            )

        messages = Message.objects.filter(
            pk__in=messages_status_qs.values_list("message_id", flat=True)
        )

        messages_status_qs.update(is_read=True, read_at=timezone.now())

        ChatRoomOnMessagesCountUpdate.send_updated_chat_count(
            profile=profile, profile_id=profile.relay_id
        )

        return ChatRoomReadMessages(room=room, profile=profile, messages=messages)


class ChatRoomUnread(RelayMutation):
    room = graphene.Field(ChatRoomObjectType)
    profile = graphene.Field(ProfileObjectType)

    class Input:
        room_id = graphene.ID(required=True)
        profile_id = graphene.ID(required=True)

    @classmethod
    @login_required
    def mutate_and_get_payload(cls, root, info, room_id, profile_id, **input) -> "ChatRoomUnread":
        room = get_obj_from_relay_id(info, room_id)
        profile = get_obj_from_relay_id(info, profile_id)

        if not info.context.user.has_perm(f"{profile_app_label}.use_profile", profile):
            return ChatRoomUnread(
                errors=[
                    ErrorType(
                        field="profile_id",
                        messages=[_("You don't have permission to act as this profile")],
                    )
                ]
            )

        if not ChatRoomParticipant.objects.filter(
            profile_id=profile.pk,
            room=room,
        ).exists():
            return ChatRoomUnread(
                errors=[
                    ErrorType(
                        field="participant",
                        messages=[_("Participant is not part of the room.")],
                    )
                ]
            )

        UnreadMessageCount.objects.update_or_create(
            profile=profile,
            room=room,
            defaults={"marked_unread": True},
        )

        return ChatRoomUnread(room=room, profile=profile)


class ChatRoomArchive(RelayMutation):
    room = graphene.Field(ChatRoomObjectType)

    class Input:
        room_id = graphene.ID(required=True)
        profile_id = graphene.ID(required=True)
        archive = graphene.Boolean(required=True)

    @classmethod
    @login_required
    def mutate_and_get_payload(
        cls, root, info, room_id, profile_id, archive, **input
    ) -> "ChatRoomArchive":
        room = get_obj_from_relay_id(info, room_id)
        profile = get_obj_from_relay_id(info, profile_id)

        if not info.context.user.has_perm(f"{profile_app_label}.use_profile", profile):
            return ChatRoomArchive(
                errors=[
                    ErrorType(
                        field="profile_id",
                        messages=[
                            _("You don't have permission to archive this chatroom as this profile")
                        ],
                    )
                ]
            )

        participant = ChatRoomParticipant.objects.filter(
            profile_id=profile.pk,
            room=room,
        ).first()

        if not participant:
            return ChatRoomArchive(
                errors=[
                    ErrorType(
                        field="participant",
                        messages=[_("Participant is not part of the room.")],
                    )
                ]
            )

        with transaction.atomic():
            participant = ChatRoomParticipant.objects.select_for_update().get(pk=participant.pk)
            participant.has_archived_room = archive
            participant.save()
            room.refresh_from_db()
        return ChatRoomArchive(room=room)


class ChatsMutations(object):
    chat_room_create = ChatRoomCreate.Field()
    chat_room_update = ChatRoomUpdate.Field()
    chat_rooms_add_participant = ChatRoomsAddParticipant.Field()
    chat_room_send_message = ChatRoomSendMessage.Field()
    chat_room_edit_message = ChatRoomEditMessage.Field()
    chat_room_delete_message = ChatRoomDeleteMessage.Field()
    chat_room_read_messages = ChatRoomReadMessages.Field()
    chat_room_unread = ChatRoomUnread.Field()
    chat_room_archive = ChatRoomArchive.Field()
    chat_room_toggle_admin = ChatRoomToggleAdmin.Field()
