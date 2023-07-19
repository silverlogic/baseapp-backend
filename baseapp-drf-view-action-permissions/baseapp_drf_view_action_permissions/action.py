from rest_framework import permissions
from rest_framework.permissions import DjangoModelPermissions

from .utils import client_ip_address_is_restricted


class DjangoActionPermissions(DjangoModelPermissions):
    """Customize permission logic based on request, action and object.

    For every viewset with `queryset` you want to override some custom logic
    for particular action, you should define such attribute for `viewset`.
    Viewset permission at common action level:
    ```
        perms_map_action = {
            '<action>': [
                <str> | <function(user, view, obj=None)>,
                ...
            ],
            ...
        }
    ```

    Viewset without queryset should specify the model_cls
    ```
    model_class = ModelName
    ```

    To enforce primary method action i.e for post request, check app.add_modelname permission and the specified
    perms_map_action
    ```
    include_model_default_method_permission = True
    ```
    """

    perms_map_action = {
        "retrieve": ["%(app_label)s.view_%(model_name)s"],
        "list": ["%(app_label)s.view_%(model_name)s_list"],
        "create": ["%(app_label)s.add_%(model_name)s"],
        "update": ["%(app_label)s.change_%(model_name)s"],
        "destroy": ["%(app_label)s.delete_%(model_name)s"],
    }

    def generate_perms_map_action(self, view):
        action = view.action
        if action:
            action = action.replace(
                "partial_", ""
            )  # Treat partial updates the same as normal updates
            if self.perms_map_action.get(action):
                return
            perm_str = "%(app_label)s.{}_%(app_label)s".format(action)
            permission_base = getattr(view, "permission_base", "")
            if permission_base:
                perm_str = "%(app_label)s.{}_{}".format(action, permission_base)

            self.perms_map_action[action] = [perm_str]

    # pylint: disable=protected-access
    def get_origin_model(self, model_cls):
        """Return origin model even if proxy has been received."""
        return model_cls._meta.proxy_for_model or model_cls._meta.model

    def get_required_permissions(self, method, model_cls):
        """Add ability to define origin model even via proxy."""
        model_cls = self.get_origin_model(model_cls)
        return super().get_required_permissions(method, model_cls)

    def get_perms_list(self, view, obj=None):
        """Return permission list for action from backend and view."""
        perms_map_name = "perms_map_action"
        view_perms_map = getattr(view, perms_map_name, {})
        view_perms_list = view_perms_map.get(view.action)
        if view_perms_list is not None:
            return view_perms_list
        self.generate_perms_map_action(view)
        backend_perms_map = getattr(self, perms_map_name, {})
        return backend_perms_map.get(view.action) or []

    # pylint: disable=protected-access
    def get_required_action_permissions(self, view, model_cls, obj=None):
        """Given a model and an action, return the list of permission codes."""
        model_cls = self.get_origin_model(model_cls)
        kwargs = {
            "app_label": model_cls._meta.app_label,
            "model_name": model_cls._meta.model_name,
        }
        return [
            perm % kwargs if isinstance(perm, str) else perm
            for perm in self.get_perms_list(view, obj)
        ]

    def user_has_action_perm(self, user, view, perm, obj=None):
        """Check if user has single permission for particular view action."""
        assert callable(perm) or isinstance(perm, str), "Permission must be function or string"

        if callable(perm):
            return perm(user, view, obj)

        return user.has_perm(perm)

    def get_model_cls(self, view):
        model_cls = getattr(view, "model_class", None)
        if not model_cls:
            queryset = self._queryset(view)
            assert queryset, "queryset or model_class is required"
            model_cls = queryset.model

        return model_cls

    def has_action_permission(self, request, view, obj=None):
        """Check action specific permissions ignoring custom method."""
        model_cls = self.get_model_cls(view)
        perms = self.get_required_action_permissions(view, model_cls, obj)
        return all(self.user_has_action_perm(request.user, view, perm, obj) for perm in perms)

    def has_permission(self, request, view):
        """Apply action permission without object and with ignoring method."""
        if getattr(view, "_ignore_model_permissions", False):
            return True

        if not request.user or (
            not request.user.is_authenticated and self.authenticated_users_only
        ):
            return False

        if view.action in getattr(view, "permission_exclude_views", []):
            return True

        if getattr(view, "include_model_default_method_permission", None):
            model_cls = self.get_model_cls(view)
            perms = self.get_required_permissions(request.method, model_cls)
            result = all(self.user_has_action_perm(request.user, view, perm) for perm in perms)
            return result and self.has_action_permission(request, view)

        return self.has_action_permission(request, view)

    def has_object_permission(self, request, view, obj):
        """Apply action permission with object and with ignoring method."""
        return self.has_action_permission(request, view, obj)


class IpAddressPermission(permissions.IsAuthenticated):
    message = "restricted by IP address"

    def has_permission(self, request, view):
        if super().has_permission(request, view):
            return not client_ip_address_is_restricted(request)
        return False
