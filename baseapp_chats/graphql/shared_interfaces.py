from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .interfaces import ChatRoomsInterface


def get_chat_rooms_interface() -> type["ChatRoomsInterface"]:
    from .interfaces import ChatRoomsInterface

    return ChatRoomsInterface
