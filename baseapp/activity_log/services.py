from typing import Any

import pghistory
from django.apps import apps
from pghistory import runtime

from baseapp_core.plugins import SharedServiceProvider

from .models import VisibilityTypes

# Context metadata key set by `set_private_activity`, so a later `set_public_activity` in the same
# request leaves the activity private.
PRIVATE_ACTIVITY_KEY = "private_activity"


def _current_context_metadata() -> dict[str, Any]:
    context = getattr(runtime._tracker, "value", None)
    return context.metadata if context else {}


class ActivityLogService(SharedServiceProvider):
    @property
    def service_name(self) -> str:
        return "activity_log"

    def is_available(self) -> bool:
        return apps.is_installed("baseapp.activity_log")

    def set_public_activity(self, verb: str, **kwargs: Any) -> None:
        """Set public visibility context for activity logging.

        Does nothing once `set_private_activity` was called in the same context.

        Args:
            verb: The action verb describing the activity (e.g., 'create', 'update')
            **kwargs: Additional context parameters to be logged
        """
        if _current_context_metadata().get(PRIVATE_ACTIVITY_KEY):
            return
        pghistory.context(visibility=VisibilityTypes.PUBLIC, verb=verb, **kwargs)

    def set_private_activity(self) -> None:
        """Keep the current activity private (the default), for the rest of the context.

        The activity log has one entry per context (a request), so this also undoes an earlier
        `set_public_activity` and ignores later ones.
        """
        pghistory.context(visibility=None, **{PRIVATE_ACTIVITY_KEY: True})
