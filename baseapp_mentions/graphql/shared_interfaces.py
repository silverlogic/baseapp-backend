from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .interfaces import MentionsInterface


def get_mentions_interface() -> "type[MentionsInterface]":
    from .interfaces import MentionsInterface

    return MentionsInterface
