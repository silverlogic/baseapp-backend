import swapper
from rest_framework import permissions

File = swapper.load_model("baseapp_files", "File")
file_app_label = File._meta.app_label
file_model_name = File._meta.model_name.lower()


class IsOwner(permissions.BasePermission):
    """
    Permission to only allow owners to access their files.
    Uses has_perm for easy override at project level.
    """

    def has_object_permission(self, request, view, obj):
        return request.user.has_perm(f"{file_app_label}.view_{file_model_name}", obj)


class IsOwnerOrReadOnly(permissions.BasePermission):
    """
    Permission to only allow owners of a file to modify it.
    Read permissions check view_file permission.
    Write permissions check change_file permission.
    Uses has_perm for easy override at project level.
    """

    def has_object_permission(self, request, view, obj):
        # Read permissions - check view permission. This API manages the caller's own
        # files (its list is scoped the same way), so view_file alone, which also admits
        # everyone for public files, is not enough.
        if request.method in permissions.SAFE_METHODS:
            perm = f"{file_app_label}.view_{file_model_name}"
            return request.user.has_perm(perm, obj) and (
                obj.created_by == request.user or request.user.has_perm(perm)
            )

        # Write permissions - check change permission
        return request.user.has_perm(f"{file_app_label}.change_{file_model_name}", obj)


class IsAuthenticatedOrAnonymousUploads(permissions.BasePermission):
    """Signed-in users, or anyone when ``BASEAPP_FILES_ALLOW_ANONYMOUS_UPLOADS`` is on."""

    def has_permission(self, request, view) -> bool:
        from ...permissions import anonymous_uploads_allowed

        return bool(request.user and request.user.is_authenticated) or anonymous_uploads_allowed()
