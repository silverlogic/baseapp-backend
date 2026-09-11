from django.conf import settings
from rest_framework.permissions import BasePermission


class E2eEnabled(BasePermission):
    def has_permission(self, request, view) -> bool:
        return bool(hasattr(settings, "E2E") and settings.E2E["ENABLED"])
