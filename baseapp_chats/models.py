import swapper

from .base import (
    AbstractBaseChatRoom,
    AbstractBaseMessage,
    AbstractChatRoomParticipant,
    AbstractMessageStatus,
    AbstractUnreadMessageCount,
)
from .triggers import (
    create_message_status_trigger,
    decrement_unread_count_trigger,
    increment_unread_count_trigger,
    set_last_message_on_insert_trigger,
    update_last_message_on_delete_trigger,
)


class ChatRoom(AbstractBaseChatRoom):
    class Meta(AbstractBaseChatRoom.Meta):
        swappable = swapper.swappable_setting("baseapp_chats", "ChatRoom")


class ChatRoomParticipant(AbstractChatRoomParticipant):
    class Meta(AbstractChatRoomParticipant.Meta):
        swappable = swapper.swappable_setting("baseapp_chats", "ChatRoomParticipant")


class UnreadMessageCount(AbstractUnreadMessageCount):
    class Meta(AbstractUnreadMessageCount.Meta):
        swappable = swapper.swappable_setting("baseapp_chats", "UnreadMessageCount")


class Message(AbstractBaseMessage):
    class Meta(AbstractBaseMessage.Meta):
        swappable = swapper.swappable_setting("baseapp_chats", "Message")
        triggers = (
            []
            if swapper.is_swapped("baseapp_chats", "Message")
            else [
                set_last_message_on_insert_trigger(ChatRoom),
                create_message_status_trigger(ChatRoomParticipant, AbstractBaseMessage.MessageType),
                update_last_message_on_delete_trigger(ChatRoom),
            ]
        )


class MessageStatus(AbstractMessageStatus):
    class Meta(AbstractMessageStatus.Meta):
        swappable = swapper.swappable_setting("baseapp_chats", "MessageStatus")
        triggers = (
            []
            if swapper.is_swapped("baseapp_chats", "MessageStatus")
            else [
                increment_unread_count_trigger(UnreadMessageCount, Message),
                decrement_unread_count_trigger(UnreadMessageCount, Message),
            ]
        )
