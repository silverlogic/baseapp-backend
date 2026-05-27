from typing import Any, Callable, Iterable, Type

import pghistory
import pghistory.core as pgh_core
import pgtrigger
from django.db.models import Model

# Registry to store pghistory track configurations
# Format: {model_class: (args, kwargs, is_override)}
# is_override: True if set by decorator, False if set by default function
_pghistory_registry: dict[Type[Model], tuple[tuple, dict[str, Any], bool]] = {}

# Registry to store pgtrigger configurations.
# Format: {model_class: (triggers, is_override)}
# is_override: True if set by decorator, False if set by default function
_pgtrigger_registry: dict[Type[Model], tuple[list[pgtrigger.Trigger], bool]] = {}


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
        if model_cls._meta.abstract:
            continue

        existing = pgh_core.event_models(
            tracks_model=model_cls,
            include_missing_pgh_obj=True,
        )
        if existing:
            continue

        pghistory.track(*args, **kwargs)(model_cls)


def pgtrigger_register_track(
    *triggers: pgtrigger.Trigger,
) -> Callable[[Type[Model]], Type[Model]]:
    """
    Decorator to register pgtrigger triggers for a model.

    This will override any default triggers registered via
    pgtrigger_register_default_track, even if the decorator is used
    before the default is registered.

    Usage:
        @pgtrigger_register_track(
            insert_document_id_trigger(),
            delete_document_id_trigger(),
        )
        class MyModel(models.Model):
            pass
    """

    def decorator(cls: Type[Model]) -> Type[Model]:
        if cls._meta.abstract:
            raise ValueError("Cannot register pgtrigger triggers on abstract models")
        _pgtrigger_registry[cls] = (list(triggers), True)
        return cls

    return decorator


def pgtrigger_register_default_track(
    model_cls: Type[Model], triggers: Iterable[pgtrigger.Trigger]
) -> Type[Model]:
    """
    Register default pgtrigger triggers for a model.

    This sets the base trigger set. If a decorator is used on the model,
    it will override this default configuration entirely.

    Usage (after `init_swapped_models(...)`):

        Message = init_swapped_models([("baseapp_chats", "Message")])
        pgtrigger_register_default_track(
            Message,
            [
                set_last_message_on_insert_trigger(ChatRoom),
                update_last_message_on_delete_trigger(ChatRoom),
            ],
        )

    The actual triggers are attached to the model's `_meta.triggers`
    by `apply_pgtrigger_tracks()` during `baseapp_core.apps.ready()`.
    """
    if model_cls._meta.abstract:
        raise ValueError("Cannot register pgtrigger triggers on abstract models")

    if model_cls not in _pgtrigger_registry or not _pgtrigger_registry[model_cls][1]:
        _pgtrigger_registry[model_cls] = (list(triggers), False)

    return model_cls


def apply_pgtrigger_tracks() -> None:
    """
    Apply registered pgtrigger triggers to their concrete models.

    Mutates each model's `_meta.triggers` list, skipping triggers
    whose `name` is already present (so re-applying is idempotent and
    we don't clobber triggers attached by other paths — e.g. the
    DocumentIdMixin `class_prepared` signal handler).

    Called from `baseapp_core.apps.PackageConfig.ready()`. Decorator
    overrides take precedence over default registrations because the
    decorator wins the `_pgtrigger_registry` entry first.
    """
    for model_cls, (triggers, _) in _pgtrigger_registry.items():
        if model_cls._meta.abstract or model_cls._meta.swapped:
            continue

        if not hasattr(model_cls._meta, "triggers"):
            model_cls._meta.triggers = []

        existing_names = {t.name for t in model_cls._meta.triggers}
        for trigger in triggers:
            if trigger.name in existing_names:
                continue
            model_cls._meta.triggers.append(trigger)
            existing_names.add(trigger.name)
