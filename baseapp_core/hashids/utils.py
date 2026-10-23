import uuid

from django.db import models


def is_uuid4(s: str) -> bool:
    try:
        val = uuid.UUID(str(s))
    except (ValueError, TypeError, AttributeError):
        return False
    # Require canonical lowercased representation and v4
    return val.version == 4 and str(val) == str(s).lower()


def has_autoincrement_pk(model_cls: type) -> bool:
    return isinstance(
        model_cls._meta.pk, (int, models.AutoField, models.BigAutoField, models.SmallAutoField)
    )


def is_model_subclass(model_cls: type | None, expected_model: type) -> bool:
    """Whether rows of `model_cls` can be returned where `expected_model` is expected.

    A proxy model is compared through its concrete model, because a content type (and so a
    DocumentId row) always points at the concrete model.
    """
    if model_cls is None:
        return False
    meta = getattr(expected_model, "_meta", None)
    expected = getattr(meta, "concrete_model", None) or expected_model
    return issubclass(model_cls, expected)
