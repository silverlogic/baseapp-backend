from collections.abc import Callable
from functools import wraps
from typing import Any

from django.conf import settings

_graphql_loaded = False


def _ensure_graphql_loaded() -> None:
    """Import the Strawberry schema (`settings.STRAWBERRY_SCHEMA`) so every type is registered."""
    global _graphql_loaded

    if _graphql_loaded:
        return
    if getattr(settings, "STRAWBERRY_SCHEMA", None):
        from baseapp_core.strawberry.schema import get_schema

        get_schema()
    _graphql_loaded = True


def graphql_schema_required(func) -> Callable:
    """Decorator that ensures the GraphQL schema (and so the type registry) is loaded first."""

    @wraps(func)
    def wrapper(*args, **kwargs) -> Any:
        _ensure_graphql_loaded()
        return func(*args, **kwargs)

    return wrapper
