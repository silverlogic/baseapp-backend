from functools import wraps
from typing import Callable


def register_hook(hook_name: str):
    """
    Decorator to mark functions as hook handlers.

    Note: Actual registration happens via entry points in setup.py.
    This decorator is kept for documentation and future use.
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)

        return wrapper

    return decorator
