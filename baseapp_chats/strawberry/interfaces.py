from collections.abc import Iterable

import strawberry
import swapper
from django.db.models import Model
from strawberry.types import Info

from baseapp_core.strawberry import CountedConnection, Node, type_for_model
from baseapp_core.strawberry.connections import connection

from ..graphql.filters import ChatRoomFilter
from ..graphql.interfaces import ChatRoomsInterface as GrapheneChatRoomsInterface

ChatRoom = swapper.load_model("baseapp_chats", "ChatRoom")


@strawberry.interface(name="ChatRoomsInterface")
class ChatRoomsInterface(Node):
    @connection(CountedConnection[type_for_model(ChatRoom)] | None, filterset_class=ChatRoomFilter)
    def chat_rooms(self, info: Info) -> Iterable[Model]:
        return GrapheneChatRoomsInterface.resolve_chat_rooms(self, info)

    @strawberry.field
    def unread_messages_count(self, info: Info) -> int | None:
        return GrapheneChatRoomsInterface.resolve_unread_messages_count(self, info)
