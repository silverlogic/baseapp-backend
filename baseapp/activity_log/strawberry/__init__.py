from typing import Any


def get_node_activity_log_interface() -> Any:
    from .interfaces import NodeActivityLogInterface

    return NodeActivityLogInterface


def get_user_activity_log_interface() -> Any:
    from .interfaces import UserActivityLogInterface

    return UserActivityLogInterface


def get_profile_activity_log_interface() -> Any:
    from .interfaces import ProfileActivityLogInterface

    return ProfileActivityLogInterface
