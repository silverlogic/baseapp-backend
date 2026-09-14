from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .object_types import ReactionsInterface


def get_reactions_interface() -> type["ReactionsInterface"]:
    from .object_types import ReactionsInterface

    return ReactionsInterface
