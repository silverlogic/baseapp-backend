from baseapp_chats.base import (
    AbstractBaseChatRoom,
    AbstractBaseMessage,
    AbstractChatRoomParticipant,
    AbstractMessageStatus,
    AbstractUnreadMessageCount,
)
from baseapp_chats.triggers import (
    create_message_status_trigger,
    decrement_unread_count_trigger,
    increment_unread_count_trigger,
    set_last_message_on_insert_trigger,
    update_last_message_on_delete_trigger,
)


class ChatRoom(AbstractBaseChatRoom):
    @classmethod
    def get_graphql_object_type(cls):
        from baseapp_chats.graphql.object_types import ChatRoomObjectType

        return ChatRoomObjectType


class ChatRoomParticipant(AbstractChatRoomParticipant):
    @classmethod
    def get_graphql_object_type(cls):
        from baseapp_chats.graphql.object_types import ChatRoomParticipantObjectType

        return ChatRoomParticipantObjectType


class UnreadMessageCount(AbstractUnreadMessageCount):
    pass


class Message(AbstractBaseMessage):
    class Meta(AbstractBaseMessage.Meta):
        triggers = [
            set_last_message_on_insert_trigger(ChatRoom),
            create_message_status_trigger(ChatRoomParticipant, AbstractBaseMessage.MessageType),
            update_last_message_on_delete_trigger(ChatRoom),
        ]

    @classmethod
    def get_graphql_object_type(cls):
        from baseapp_chats.graphql.object_types import MessageObjectType

        return MessageObjectType


class MessageStatus(AbstractMessageStatus):
    class Meta(AbstractMessageStatus.Meta):
        triggers = [
            increment_unread_count_trigger(UnreadMessageCount, Message),
            decrement_unread_count_trigger(UnreadMessageCount, Message),
        ]
