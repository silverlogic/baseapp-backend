import swapper
from baseapp_notifications import send_notification
from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _

Message = swapper.load_model("baseapp_chats", "Message")
MessageStatus = swapper.load_model("baseapp_chats", "MessageStatus")
UnreadMessageCount = swapper.load_model("baseapp_chats", "UnreadMessageCount")
Verbs = Message.Verbs

User = get_user_model()


def send_message(
    room,
    profile,
    user,
    content,
    room_id=None,
    verb=Verbs.SENT_MESSAGE,
    action_object=None,
    extra_data=None,
    in_reply_to=None,
):
    message = Message.objects.create(
        user=user,
        profile=profile,
        content=content,
        room=room,
        verb=verb,
        in_reply_to=in_reply_to,
        action_object=action_object,
        extra_data=extra_data,
    )

    from baseapp_chats.graphql.subscriptions import ChatRoomOnNewMessage

    ChatRoomOnNewMessage.new_message(room_id=room_id or room.relay_id, message=message)

    room.last_message_time = message.created
    room.last_message = message
    room.save()

    return message


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
