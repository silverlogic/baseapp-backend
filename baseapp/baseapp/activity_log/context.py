from typing import Any

import pghistory

from .models import VisibilityTypes


def set_public_activity(verb: str, **kwargs: Any) -> None:
    """Set public visibility context for activity logging.

    Args:
        verb: The action verb describing the activity (e.g., 'create', 'update')
        **kwargs: Additional context parameters to be logged
    """
    pghistory.context(visibility=VisibilityTypes.PUBLIC, verb=verb, **kwargs)
