import base64
import binascii
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


def to_global_id(type_name: str, id: object) -> str:
    """Relay legacy global id: base64 of `<TypeName>:<id>`."""
    return base64.b64encode(f"{type_name}:{id}".encode()).decode()


def from_global_id(global_id: str) -> tuple[str, str]:
    """`(type_name, id)` of a legacy global id; `("", "")` when it isn't one."""
    try:
        decoded = base64.b64decode(str(global_id), validate=True).decode()
    except (binascii.Error, UnicodeDecodeError, ValueError):
        return "", ""
    if ":" not in decoded:
        return "", decoded
    type_name, _, id = decoded.partition(":")
    return type_name, id
