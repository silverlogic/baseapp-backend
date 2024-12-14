import graphene
import swapper
from baseapp_core.graphql import (
    RelayMutation,
    get_obj_from_relay_id,
    get_pk_from_relay_id,
    login_required,
)
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from graphene_django.types import ErrorType

from baseapp_chats.graphql.subscriptions import ChatRoomOnMessagesCountUpdate
from baseapp_chats.utils import send_message, send_new_chat_message_notification

ChatRoom = swapper.load_model("baseapp_chats", "ChatRoom")
ChatRoomParticipant = swapper.load_model("baseapp_chats", "ChatRoomParticipant")
Message = swapper.load_model("baseapp_chats", "Message")
MessageStatus = swapper.load_model("baseapp_chats", "MessageStatus")
UnreadMessageCount = swapper.load_model("baseapp_chats", "UnreadMessageCount")
Block = swapper.load_model("baseapp_blocks", "Block")
User = get_user_model()
Profile = swapper.load_model("baseapp_profiles", "Profile")


ChatRoomObjectType = ChatRoom.get_graphql_object_type()
ProfileObjectType = Profile.get_graphql_object_type()
MessageObjectType = Message.get_graphql_object_type()
ChatRoomParticipantObjectType = ChatRoomParticipant.get_graphql_object_type()


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

        if not info.context.user.has_perm("baseapp_profiles.use_profile", profile):
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
        room = ChatRoom.objects.create(
            created_by=info.context.user,
            last_message_time=timezone.now(),
            is_group=is_group,
            title=title,
            image=image,
        )

        ChatRoomParticipant.objects.bulk_create(
            [
                ChatRoomParticipant(profile=participant, room=room, accepted_at=timezone.now())
                for participant in participants
            ]
        )

        return ChatRoomCreate(
            profile=profile,
            room=ChatRoomObjectType._meta.connection.Edge(
                node=room,
            ),
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

        if not info.context.user.has_perm("baseapp_profiles.use_profile", profile):
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

        if not info.context.user.has_perm("baseapp_profiles.use_profile", profile):
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

        if not info.context.user.has_perm("baseapp_profiles.use_profile", profile):
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

        if not info.context.user.has_perm("baseapp_profiles.use_profile", profile):
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
    chat_room_send_message = ChatRoomSendMessage.Field()
    chat_room_read_messages = ChatRoomReadMessages.Field()
    chat_room_unread = ChatRoomUnread.Field()
    chat_room_archive = ChatRoomArchive.Field()
