from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .interfaces import NotificationsInterface


def get_notifications_interface() -> type["NotificationsInterface"]:
    from .interfaces import NotificationsInterface

    return NotificationsInterface
