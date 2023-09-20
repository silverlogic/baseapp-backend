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
        # Read permissions - check view permission
        if request.method in permissions.SAFE_METHODS:
            return request.user.has_perm(f"{file_app_label}.view_{file_model_name}", obj)

        # Write permissions - check change permission
        return request.user.has_perm(f"{file_app_label}.change_{file_model_name}", obj)
