import channels_graphql_ws
import graphene
import swapper
from baseapp_core.graphql import get_obj_from_relay_id
from channels.db import database_sync_to_async

Profile = swapper.load_model("baseapp_profiles", "Profile")
ChatRoom = swapper.load_model("baseapp_chats", "ChatRoom")
Message = swapper.load_model("baseapp_chats", "Message")
MessageObjectType = Message.get_graphql_object_type()
ProfileObjectType = Profile.get_graphql_object_type()


class ChatRoomOnRoomUpdate(channels_graphql_ws.Subscription):
    room = graphene.Field(lambda: ChatRoom.get_graphql_object_type()._meta.connection.Edge)

    class Arguments:
        profile_id = graphene.ID(required=True)

    @staticmethod
    def subscribe(root, info, **kwargs):
        return ["chat"]

    @staticmethod
    def publish(payload, info, **kwargs):
        message = payload["message"]
        user = info.context.channels_scope["user"]
        room = message.room

        if not user.is_authenticated or not user.has_perm("baseapp_chats.view_chatroom", room):
            return None

        # TO DO: only send the message to the participants, check for profile_id

        Edge = ChatRoom.get_graphql_object_type()._meta.connection.Edge
        return ChatRoomOnRoomUpdate(room=Edge(node=room))

    @classmethod
    def new_message(cls, message, **kwargs):
        cls.broadcast(
            group="chat",
            payload={"message": message},
        )


class ChatRoomOnMessagesCountUpdate(channels_graphql_ws.Subscription):
    profile = graphene.Field(ProfileObjectType)

    class Arguments:
        profile_id = graphene.ID(required=True)

    @staticmethod
    def subscribe(root, info, profile_id):
        user = info.context.channels_scope["user"]
        profile = database_sync_to_async(get_obj_from_relay_id)(info, profile_id)

        # TO DO: change to a better permission check, maybe baseapp_chats.view_chatroom
        if not user.is_authenticated or not database_sync_to_async(user.has_perm)(
            "baseapp_profiles.use_profile", profile
        ):
            return []
        return [profile_id]

    @staticmethod
    def publish(payload, info, profile_id):
        profile = payload["profile"]

        return ChatRoomOnMessagesCountUpdate(profile=profile)

    @classmethod
    def send_updated_chat_count(cls, profile, profile_id):
        cls.broadcast(
            group=profile_id,
            payload={"profile": profile},
        )


class ChatRoomOnNewMessage(channels_graphql_ws.Subscription):
    message = graphene.Field(lambda: MessageObjectType._meta.connection.Edge)

    class Arguments:
        room_id = graphene.ID(required=True)

    @staticmethod
    def subscribe(root, info, room_id):
        room = database_sync_to_async(get_obj_from_relay_id)(info, room_id)

        user = info.context.channels_scope["user"]
        if not user.is_authenticated or not database_sync_to_async(user.has_perm)(
            "baseapp_chats.view_chatroom", room
        ):
            return []
        return [room_id]

    @staticmethod
    def publish(payload, info, room_id):
        message = payload["message"]
        user = info.context.channels_scope["user"]

        if not user.is_authenticated:
            return None

        return ChatRoomOnNewMessage(message=MessageObjectType._meta.connection.Edge(node=message))

    @classmethod
    def new_message(cls, message, room_id):
        cls.broadcast(
            group=room_id,
            payload={"message": message},
        )
        ChatRoomOnRoomUpdate.new_message(message=message)


class ChatsSubscriptions:
    chat_room_on_new_message = ChatRoomOnNewMessage.Field()
    chat_room_on_room_update = ChatRoomOnRoomUpdate.Field()
    chat_room_on_messages_count_update = ChatRoomOnMessagesCountUpdate.Field()
