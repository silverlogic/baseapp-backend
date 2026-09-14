import traceback
from functools import wraps
from typing import Callable, ParamSpec, TypeVar

from django.apps import apps
from django.core.exceptions import ImproperlyConfigured

P = ParamSpec("P")
T = TypeVar("T")


def _build_early_access_exception(accessor_name: str) -> ImproperlyConfigured:
    """
    Build a consistent early-access error for shared registries.
    """
    stack = "".join(traceback.format_stack())
    return ImproperlyConfigured(
        f"{accessor_name} was called before Django app loading finished.\n"
        "Most likely reason: this code path is executed in an early import context "
        "(module-level import/scope) before AppConfig.ready() registers shared layers.\n"
        "Move the call to runtime (inside a function/method) so it executes after app startup.\n\n"
        f"Backtrace:\n{stack}"
    )


def require_django_ready(func: Callable[P, T]) -> Callable[P, T]:
    """
    Decorator that blocks access until Django app loading is complete.
    """

    @wraps(func)
    def _wrapped(*args: P.args, **kwargs: P.kwargs) -> T:
        if not apps.ready:
            accessor_name = f"{func.__qualname__}()"
            raise _build_early_access_exception(accessor_name)
        return func(*args, **kwargs)

    return _wrapped
