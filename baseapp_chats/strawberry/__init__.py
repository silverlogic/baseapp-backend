from typing import Any


def get_chat_rooms_interface() -> Any:
    from .interfaces import ChatRoomsInterface

    return ChatRoomsInterface
