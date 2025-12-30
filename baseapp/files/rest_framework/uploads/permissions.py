from rest_framework import permissions


class IsOwner(permissions.BasePermission):
    """
    Permission to only allow owners to access their files.
    """

    def has_object_permission(self, request, view, obj):
        return obj.created_by == request.user


class IsOwnerOrReadOnly(permissions.BasePermission):
    """
    Permission to only allow owners of a file to modify it.
    Read permissions are allowed to authenticated users.
    """

    def has_object_permission(self, request, view, obj):
        # Read permissions allowed to authenticated users
        if request.method in permissions.SAFE_METHODS:
            return True

        # Write permissions only to owner
        return obj.created_by == request.user
