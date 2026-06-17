def get_node_activity_log_interface():
    from .interfaces import NodeActivityLogInterface

    return NodeActivityLogInterface


def get_user_activity_log_interface():
    from .interfaces import UserActivityLogInterface

    return UserActivityLogInterface


def get_profile_activity_log_interface():
    from .interfaces import ProfileActivityLogInterface

    return ProfileActivityLogInterface
