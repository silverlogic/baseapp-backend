import strawberry
import swapper

from baseapp_core.strawberry import type_for_model
from baseapp_core.strawberry.relay import typed_node_field

ChatRoom = swapper.load_model("baseapp_chats", "ChatRoom")


@strawberry.type
class ChatsQueries:
    chat_room = typed_node_field(type_for_model(ChatRoom))
