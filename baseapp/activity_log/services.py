from typing import Any

import pghistory
from django.apps import apps

from baseapp_core.plugins import SharedServiceProvider

from .models import VisibilityTypes


class ActivityLogService(SharedServiceProvider):
    @property
    def service_name(self) -> str:
        return "activity_log"

    def is_available(self) -> bool:
        return apps.is_installed("baseapp.activity_log")

    def set_public_activity(self, verb: str, **kwargs: Any) -> None:
        """Set public visibility context for activity logging.

        Args:
            verb: The action verb describing the activity (e.g., 'create', 'update')
            **kwargs: Additional context parameters to be logged
        """
        pghistory.context(visibility=VisibilityTypes.PUBLIC, verb=verb, **kwargs)
