import uuid

from django.db import models


def is_uuid4(s: str) -> bool:
    try:
        val = uuid.UUID(s, version=4)
    except ValueError:
        return False
    return str(val) == s.lower()


def has_autoincrement_pk(model_cls: type) -> bool:
    return isinstance(model_cls._meta.pk, (int, models.AutoField, models.BigAutoField))
