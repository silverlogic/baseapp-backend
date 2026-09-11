from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .object_types import CommentsInterface


def get_comments_interface() -> type["CommentsInterface"]:
    from .object_types import CommentsInterface

    return CommentsInterface
