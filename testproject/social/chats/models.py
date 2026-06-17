from baseapp_chats.models import (
    AbstractBaseChatRoom,
    AbstractBaseMessage,
    AbstractChatRoomParticipant,
    AbstractMessageStatus,
    AbstractUnreadMessageCount,
)


class ChatRoom(AbstractBaseChatRoom):
    class Meta(AbstractBaseChatRoom.Meta):
        pass


class ChatRoomParticipant(AbstractChatRoomParticipant):
    class Meta(AbstractChatRoomParticipant.Meta):
        pass


class UnreadMessageCount(AbstractUnreadMessageCount):
    class Meta(AbstractUnreadMessageCount.Meta):
        pass


class Message(AbstractBaseMessage):
    class Meta(AbstractBaseMessage.Meta):
        pass


class MessageStatus(AbstractMessageStatus):
    class Meta(AbstractMessageStatus.Meta):
        pass
