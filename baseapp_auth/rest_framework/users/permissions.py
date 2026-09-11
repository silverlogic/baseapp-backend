from rest_framework.permissions import BasePermission


class IsAnonymous(BasePermission):
    def has_permission(self, request, view) -> bool:
        return not request.user or not request.user.is_authenticated
