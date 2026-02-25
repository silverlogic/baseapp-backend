from typing import Any, Callable, Type

import pghistory
from django.db.models import Model

# Registry to store pghistory track configurations
# Format: {model_class: (args, kwargs, is_override)}
# is_override: True if set by decorator, False if set by default function
_pghistory_registry: dict[Type[Model], tuple[tuple, dict[str, Any], bool]] = {}


def pghistory_register_track(*args: Any, **kwargs: Any) -> Callable[[Type[Model]], Type[Model]]:
    """
    Decorator to register a pghistory track configuration for a model.

    This will override any default tracks registered via pghistory_register_default_track,
    even if the decorator is used before the default is registered.

    Usage:
        @pghistory_register_track(
            pghistory.InsertEvent(),
            pghistory.UpdateEvent(),
            exclude=["field1", "field2"]
        )
        class MyModel(models.Model):
            pass

    Args:
        *args: Positional arguments to pass to pghistory.track
        **kwargs: Keyword arguments to pass to pghistory.track

    Returns:
        Decorator function that takes a model class and returns it
    """

    def decorator(cls: Type[Model]) -> Type[Model]:
        """Inner decorator function."""
        if cls._meta.abstract:
            raise ValueError("Cannot register pghistory track on abstract models")

        # Register or override the track configuration (mark as override)
        _pghistory_registry[cls] = (args, kwargs, True)
        return cls

    return decorator


def pghistory_register_default_track(
    model_cls: Type[Model], *args: Any, **kwargs: Any
) -> Type[Model]:
    """
    Function to register a default pghistory track configuration for a model.

    This sets the base track configuration. If a decorator is used on the model,
    it will override this default configuration.

    Usage:
        pghistory_register_default_track(
            MyModel,
            pghistory.InsertEvent(),
            pghistory.UpdateEvent(),
            exclude=["field1", "field2"]
        )

    Args:
        model_cls: Model class to register
        *args: Positional arguments to pass to pghistory.track
        **kwargs: Keyword arguments to pass to pghistory.track

    Returns:
        The model class that was registered
    """
    if model_cls._meta.abstract:
        raise ValueError("Cannot register pghistory track on abstract models")

    # Only register if not already overridden by decorator
    if model_cls not in _pghistory_registry or not _pghistory_registry[model_cls][2]:
        _pghistory_registry[model_cls] = (args, kwargs, False)

    return model_cls


def apply_pghistory_tracks() -> None:
    """
    Apply all registered pghistory tracks to their respective models.

    This should be called in the app's ready() method after all models are loaded.
    Decorator overrides take precedence over default tracks.
    """
    for model_cls, (args, kwargs, _) in _pghistory_registry.items():
        if not model_cls._meta.abstract:
            pghistory.track(*args, **kwargs)(model_cls)
