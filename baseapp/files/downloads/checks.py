from typing import Any

from django.core.checks import Error, register
from django.core.exceptions import FieldDoesNotExist
from django.db import models

from .registry import protected_files


@register()
def check_protected_files(app_configs: Any = None, **kwargs: Any) -> list[Error]:
    """Every registered protected file names a file field and a lookup field of its model."""
    errors = []
    for spec in protected_files:
        label = f"{spec.model._meta.label}.{spec.field}"
        try:
            field = spec.model._meta.get_field(spec.field)
        except FieldDoesNotExist:
            errors.append(
                Error(
                    f"Protected file {spec.key!r} names {label}, which does not exist.",
                    id="baseapp_files.E010",
                )
            )
            continue
        if not isinstance(field, models.FileField):
            errors.append(
                Error(
                    f"Protected file {spec.key!r} names {label}, which is not a FileField.",
                    id="baseapp_files.E011",
                )
            )
        if spec.lookup_field != "pk" and not spec.uses_public_id():
            try:
                spec.model._meta.get_field(spec.lookup_field)
            except FieldDoesNotExist:
                errors.append(
                    Error(
                        f"Protected file {spec.key!r}: lookup_field {spec.lookup_field!r} is not "
                        f"a field of {spec.model._meta.label}.",
                        id="baseapp_files.E012",
                    )
                )
    return errors
