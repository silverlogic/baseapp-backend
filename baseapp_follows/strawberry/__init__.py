from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .interfaces import FollowsInterface


def get_follows_interface() -> type["FollowsInterface"]:
    from .interfaces import FollowsInterface

    return FollowsInterface
