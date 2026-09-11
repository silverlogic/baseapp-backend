from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .interfaces import (
        NodeActivityLogInterface,
        ProfileActivityLogInterface,
        UserActivityLogInterface,
    )


def get_node_activity_log_interface() -> type["NodeActivityLogInterface"]:
    from .interfaces import NodeActivityLogInterface

    return NodeActivityLogInterface


def get_user_activity_log_interface() -> type["UserActivityLogInterface"]:
    from .interfaces import UserActivityLogInterface

    return UserActivityLogInterface


def get_profile_activity_log_interface() -> type["ProfileActivityLogInterface"]:
    from .interfaces import ProfileActivityLogInterface

    return ProfileActivityLogInterface
