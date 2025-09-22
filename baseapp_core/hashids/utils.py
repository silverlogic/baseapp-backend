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
