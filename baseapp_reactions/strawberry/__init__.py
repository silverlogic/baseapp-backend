from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .interfaces import ReactionsInterface


def get_reactions_interface() -> type["ReactionsInterface"]:
    from .interfaces import ReactionsInterface

    return ReactionsInterface
