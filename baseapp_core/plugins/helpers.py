import numbers
from typing import Any, Callable

from django.apps import apps


def apply_if_installed(
    app_name: str,
    response: Any,
    fallback_response: Any = None,
    *,
    fallback_match_response_type: bool = True,
    execute_callable: bool = False,
    callable_args: list | None = None,
    callable_kwargs: dict | None = None,
) -> Any:
    """
    Return a value or callable result if an app is installed; otherwise a fallback.

    When the app is not installed and fallback_match_response_type is True, the
    return value is inferred from the type of response: list -> [], dict -> {},
    str -> "", numbers -> None, bool -> False, set/frozenset/tuple -> empty of
    same type. For callables, fallback_response is used unless a type can be
    inferred from fallback_response.

    Args:
        app_name: The name of the app to check if it is installed.
        response: The value or callable to apply if the app is installed.
        fallback_response: Value or callable used when app is not installed and
            fallback_match_response_type is False or type cannot be inferred.
        fallback_match_response_type: If True, when app is not installed return
            a value matching the type of response (e.g. list -> []); otherwise
            use fallback_response.
        execute_callable: Whether to execute the callable if it is provided.
        callable_args: Arguments to pass to the callable when executing it.
        callable_kwargs: Keyword arguments to pass to the callable when executing it.
    """
    args = callable_args if callable_args is not None else []
    kwargs = callable_kwargs if callable_kwargs is not None else {}

    if apps.is_installed(app_name):
        if isinstance(response, Callable) and execute_callable:
            return response(*args, **kwargs)
        return response

    if fallback_match_response_type and fallback_response is None:
        return _fallback_by_response_type(response)

    if isinstance(fallback_response, Callable) and execute_callable:
        return fallback_response(*args, **kwargs)

    return fallback_response


def _fallback_by_response_type(response: Any) -> Any:
    """Return a type-matched fallback value based on the type of response."""
    if isinstance(response, bool):
        return False
    if isinstance(response, list):
        return []
    if isinstance(response, dict):
        return {}
    if isinstance(response, str):
        return ""
    if isinstance(response, numbers.Number):
        return None
    if isinstance(response, (set, frozenset, tuple)):
        return type(response)()
    return None
