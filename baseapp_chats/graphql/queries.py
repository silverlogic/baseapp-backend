import swapper

from baseapp_core.graphql import Node, get_object_type_for_model

ChatRoom = swapper.load_model("baseapp_chats", "ChatRoom")


class ChatsQueries:
    chat_room = Node.Field(get_object_type_for_model(ChatRoom))
