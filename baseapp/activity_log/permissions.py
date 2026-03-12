from django.apps import apps
from django.contrib.auth.backends import BaseBackend


class BaseActivityLogPermissionsBackend(BaseBackend):
    # Permission constants
    PERM_LIST_ANY_VISIBILITY = "activity_log.list_activitylog_any_visibility"
    PERM_LIST_USER = "activity_log.list_user_activitylog"
    PERM_LIST_NODE = "activity_log.list_node_activitylog"
    PERM_VIEW = "activity_log.view_activitylog"
    PERM_VIEW_NODE_DATA = "activity_log.view_nodelogevent-data"
    PERM_VIEW_NODE_DIFF = "activity_log.view_nodelogevent-diff"

    # Permissions that are always granted
    PUBLIC_PERMISSIONS = {
        PERM_LIST_USER,
        PERM_LIST_NODE,
        PERM_VIEW,
        PERM_VIEW_NODE_DIFF,
    }

    def has_perm(self, user_obj, perm, obj=None):
        # Public permissions
        if perm in self.PUBLIC_PERMISSIONS:
            return True

        # Superuser-only permissions
        if perm in {
            self.PERM_LIST_ANY_VISIBILITY,
            self.PERM_VIEW_NODE_DATA,
            self.PERM_VIEW_NODE_DIFF,
        }:
            return bool(user_obj.is_superuser)


activity_log_permissions_classes = []
activity_log_public_permissions = set()

if apps.is_installed("baseapp_profiles"):

    class ProfileActivityLogPermissionsBackend(BaseActivityLogPermissionsBackend):
        PERM_LIST_PROFILE = "activity_log.list_profile_activitylog"

    activity_log_permissions_classes.append(ProfileActivityLogPermissionsBackend)
    activity_log_public_permissions.add(ProfileActivityLogPermissionsBackend.PERM_LIST_PROFILE)


class ActivityLogPermissionsBackend(
    [*activity_log_permissions_classes, BaseActivityLogPermissionsBackend]
):
    PUBLIC_PERMISSIONS = {
        *BaseActivityLogPermissionsBackend.PUBLIC_PERMISSIONS * activity_log_public_permissions
    }
