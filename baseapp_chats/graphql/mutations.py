import graphene
import swapper
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from graphene_django.types import ErrorType
from rest_framework import serializers

from baseapp_chats.graphql.subscriptions import (
    ChatRoomOnMessage,
    ChatRoomOnMessagesCountUpdate,
    ChatRoomOnRoomUpdate,
)
from baseapp_chats.utils import (
    CONTENT_LINKED_PROFILE_ACTOR,
    send_message,
    send_new_chat_message_notification,
)
from baseapp_core.graphql import (
    RelayMutation,
    get_obj_from_relay_id,
    get_pk_from_relay_id,
    login_required,
)

ChatRoom = swapper.load_model("baseapp_chats", "ChatRoom")
ChatRoomParticipant = swapper.load_model("baseapp_chats", "ChatRoomParticipant")
ChatRoomParticipantRoles = ChatRoomParticipant.ChatRoomParticipantRoles
Message = swapper.load_model("baseapp_chats", "Message")
MessageStatus = swapper.load_model("baseapp_chats", "MessageStatus")
UnreadMessageCount = swapper.load_model("baseapp_chats", "UnreadMessageCount")
Block = swapper.load_model("baseapp_blocks", "Block")
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
    def mutate_and_get_payload(cls, root, info, profile_id, participants, is_group, **input):
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
        if Block.objects.filter(
            Q(actor_id=profile.id, target_id__in=participants_ids)
            | Q(actor_id__in=participants_ids, target_id=profile.id)
        ).exists():
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
            send_message(
                message_type=Message.MessageType.SYSTEM_GENERATED,
                room=room,
                profile=None,
                user=None,
                content=CONTENT_LINKED_PROFILE_ACTOR + ' created group "' + title + '"',
                content_linked_profile_actor=profile,
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
    ):
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
        image = info.context.FILES.get("image", None)

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
        if Block.objects.filter(
            Q(actor_id=profile.id, target_id__in=add_participants_pks)
            | Q(actor_id__in=add_participants_pks, target_id=profile.id)
        ).exists():
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
            unique_participants_pks = list(set(add_participants_pks))
            existing_participants_pks = ChatRoomParticipant.objects.filter(
                Q(room=room) & Q(profile__pk__in=unique_participants_pks)
            ).values_list("profile__pk", flat=True)

            new_participants = [
                participant
                for participant in unique_participants_pks
                if int(participant) not in existing_participants_pks
            ]

            created_participants = ChatRoomParticipant.objects.bulk_create(
                [
                    ChatRoomParticipant(
                        profile_id=participant,
                        room=room,
                        role=ChatRoomParticipantRoles.MEMBER,
                        accepted_at=timezone.now(),
                    )
                    for participant in new_participants
                ]
            )

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

        return ChatRoomUpdate(
            room=ChatRoomObjectType._meta.connection.Edge(
                node=room,
            ),
            removed_participants=removed_participants,
            added_participants=created_participants,
        )


class ChatRoomSendMessage(RelayMutation):
    message = graphene.Field(MessageObjectType._meta.connection.Edge)

    class Input:
        room_id = graphene.ID(required=True)
        profile_id = graphene.ID(required=True)
        content = graphene.String(required=True)
        in_reply_to_id = graphene.ID(required=False)

    @classmethod
    @login_required
    def mutate_and_get_payload(
        cls, root, info, room_id, content, profile_id, in_reply_to_id=None, **input
    ):
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

    @classmethod
    @login_required
    def mutate_and_get_payload(cls, root, info, **input):
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
    def mutate_and_get_payload(cls, root, info, **input):
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
    def mutate_and_get_payload(cls, root, info, room_id, profile_id, message_ids=None, **input):
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
    def remove_marked_unread(cls, room, profile):
        UnreadMessageCount.objects.filter(profile=profile, room=room, marked_unread=True).update(
            marked_unread=False
        )

    @classmethod
    def read_messages(cls, room, profile, message_ids=None):
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
    def mutate_and_get_payload(cls, root, info, room_id, profile_id, **input):
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
    def mutate_and_get_payload(cls, root, info, room_id, profile_id, archive, **input):
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
    chat_room_send_message = ChatRoomSendMessage.Field()
    chat_room_edit_message = ChatRoomEditMessage.Field()
    chat_room_delete_message = ChatRoomDeleteMessage.Field()
    chat_room_read_messages = ChatRoomReadMessages.Field()
    chat_room_unread = ChatRoomUnread.Field()
    chat_room_archive = ChatRoomArchive.Field()
