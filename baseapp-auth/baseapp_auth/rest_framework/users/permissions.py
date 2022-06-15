from django.conf import settings

from rest_framework import permissions

# The following actions were taken from the mappings defined on our custom DefaultRouter (apps/api/v1/routers.py)
DEFAULT_ACTIONS = ["list", "update", "partial_update", "create", "retrieve", "destroy"]
REQUEST_METHOD_ACTIONS = {
    "GET": "list",
    "POST": "create",
    "PUT": "update",
    "PATCH": "update",  # An "update" permission affects PUT and PATCH requests
    "DELETE": "destroy",
    "OPTIONS": "",
}


def get_permission_name(base_name, request_method, action):
    action = action.replace("partial_", "")  # Treat partial updates the same as normal updates

    if action in DEFAULT_ACTIONS:
        return f"{base_name}_{action}"
    if base_name == action:
        return f"{base_name}_{REQUEST_METHOD_ACTIONS[request_method]}"
    return f"{base_name}_{action}_{REQUEST_METHOD_ACTIONS[request_method]}"


class ActionPermission(permissions.BasePermission):
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        if settings.SUPERUSER_HAS_ALL_ACTION_PERMISSIONS and request.user.is_superuser:
            return True

        get_permission_base = getattr(view, "get_permission_base", None)
        permission_base = (
            view.get_permission_base() if callable(get_permission_base) else view.permission_base
        )
        permission_name = get_permission_name(permission_base, request.method, view.action)

        user_permissions = request.user.permissions
        if user_permissions and permission_name in user_permissions:
            return True

        excludes = getattr(view, "permission_exclude_views", [])
        if permission_name in excludes or view.action in excludes:
            return True

        return False
