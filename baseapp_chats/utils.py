import swapper
from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _

from baseapp_notifications import send_notification

CONTENT_LINKED_PROFILE_ACTOR = "{content_linked_profile_actor}"
CONTENT_LINKED_PROFILE_TARGET = "{content_linked_profile_target}"

SYSTEM_MESSAGE_GROUP_CREATED = CONTENT_LINKED_PROFILE_ACTOR + ' created group "{title}"'
SYSTEM_MESSAGE_GROUP_RENAMED = CONTENT_LINKED_PROFILE_ACTOR + ' changed the group name to "{title}"'
SYSTEM_MESSAGE_GROUP_IMAGE_CHANGED = CONTENT_LINKED_PROFILE_ACTOR + " changed the group image"
SYSTEM_MESSAGE_PARTICIPANT_ADDED = (
    CONTENT_LINKED_PROFILE_ACTOR + " added " + CONTENT_LINKED_PROFILE_TARGET
)
SYSTEM_MESSAGE_PARTICIPANT_REMOVED = (
    CONTENT_LINKED_PROFILE_ACTOR + " removed " + CONTENT_LINKED_PROFILE_TARGET
)
SYSTEM_MESSAGE_PARTICIPANT_LEFT = CONTENT_LINKED_PROFILE_ACTOR + " has left the group"
SYSTEM_MESSAGE_MADE_ADMIN = (
    CONTENT_LINKED_PROFILE_ACTOR + " made " + CONTENT_LINKED_PROFILE_TARGET + " an admin"
)

Message = swapper.load_model("baseapp_chats", "Message")
MessageStatus = swapper.load_model("baseapp_chats", "MessageStatus")
UnreadMessageCount = swapper.load_model("baseapp_chats", "UnreadMessageCount")
Verbs = Message.Verbs
MessageType = Message.MessageType

User = get_user_model()


def send_message(
    room,
    profile,
    user,
    content,
    content_linked_profile_actor=None,
    content_linked_profile_target=None,
    room_id=None,
    message_type=MessageType.USER_MESSAGE,
    verb=Verbs.SENT_MESSAGE,
    action_object=None,
    extra_data=None,
    in_reply_to=None,
):
    message = Message.objects.create(
        user=user,
        profile=profile,
        content=content,
        content_linked_profile_actor=content_linked_profile_actor,
        content_linked_profile_target=content_linked_profile_target,
        room=room,
        message_type=message_type,
        verb=verb,
        in_reply_to=in_reply_to,
        action_object=action_object,
        extra_data=extra_data,
    )
    from baseapp_chats.graphql.subscriptions import ChatRoomOnMessage

    room.last_message_time = message.created
    room.last_message = message
    room.save()

    ChatRoomOnMessage.new_message(room_id=room_id or room.relay_id, message=message)

    return message


def send_system_message(room, content, actor=None, target=None, extra_data=None):
    """Create a SYSTEM_GENERATED message, wrapping the send_message boilerplate."""
    if not getattr(settings, "BASEAPP_CHATS_ENABLE_SYSTEM_MESSAGES", True):
        return None
    return send_message(
        room=room,
        profile=None,
        user=None,
        message_type=MessageType.SYSTEM_GENERATED,
        content=content,
        content_linked_profile_actor=actor,
        content_linked_profile_target=target,
        extra_data=extra_data,
    )


def send_chatroom_update_system_messages(
    room,
    actor,
    *,
    new_title=None,
    title_changed=False,
    image_changed=False,
    added_participants=(),
    removed_participants=(),
    is_leaving=False,
):
    """Emit the SYSTEM_GENERATED messages describing what changed during a group update."""
    if title_changed:
        send_system_message(
            room, SYSTEM_MESSAGE_GROUP_RENAMED.replace("{title}", new_title or ""), actor=actor
        )

    if image_changed:
        send_system_message(room, SYSTEM_MESSAGE_GROUP_IMAGE_CHANGED, actor=actor)

    for participant in added_participants:
        send_system_message(
            room, SYSTEM_MESSAGE_PARTICIPANT_ADDED, actor=actor, target=participant.profile
        )

    if is_leaving:
        send_system_message(room, SYSTEM_MESSAGE_PARTICIPANT_LEFT, actor=actor)
    else:
        for participant in removed_participants:
            send_system_message(
                room, SYSTEM_MESSAGE_PARTICIPANT_REMOVED, actor=actor, target=participant.profile
            )


def send_new_chat_message_notification(room, message, info):
    for participant in room.participants.all():
        recipients = participant.profile.get_all_users()
        for recipient in recipients:
            send_notification(
                add_to_history=False,
                send_email=False,
                send_push=True,
                sender=message.profile,
                recipient=recipient,
                verb="CHATS.NEW_CHAT_MESSAGE",
                action_object=message,
                target=room,
                level="info",
                description=_("You got a new message"),
                notification_url=f"{settings.FRONT_URL}/chat?roomId={room.relay_id}",
                push_title=_("New message"),
                push_description=_("You got a new message"),
            )
