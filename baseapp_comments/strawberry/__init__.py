from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .interfaces import CommentsInterface


def get_comments_interface() -> type["CommentsInterface"]:
    from .interfaces import CommentsInterface

    return CommentsInterface
