from django.contrib.auth.backends import BaseBackend


class ActivityLogPermissionsBackend(BaseBackend):
    # Permission constants
    PERM_LIST_ANY_VISIBILITY = "activity_log.list_activitylog_any_visibility"
    PERM_LIST_USER = "activity_log.list_user_activitylog"
    PERM_LIST_PROFILE = "activity_log.list_profile_activitylog"
    PERM_LIST_NODE = "activity_log.list_node_activitylog"
    PERM_VIEW = "activity_log.view_activitylog"
    PERM_VIEW_NODE_DATA = "activity_log.view_nodelogevent-data"
    PERM_VIEW_NODE_DIFF = "activity_log.view_nodelogevent-diff"

    # Permissions that are always granted
    PUBLIC_PERMISSIONS = {
        PERM_LIST_USER,
        PERM_LIST_PROFILE,
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
