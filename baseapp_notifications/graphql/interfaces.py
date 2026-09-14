from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .object_types import NotificationsInterface


def get_notifications_interface() -> type["NotificationsInterface"]:
    from .object_types import NotificationsInterface

    return NotificationsInterface
