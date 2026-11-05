from typing import Any, Optional

from django.db import models
from rest_framework import serializers

from .registry import ProtectedFileSpec, protected_files
from .services import describe_protected_file


class ProtectedFileSerializerField(serializers.Field):
    """
    Read-only ``{key, object_id, file_name, content_type, size}`` for a registered file
    field, or null when it is empty or the request's user may not download it. Clients mint
    a link with the ``protectedFileLink`` mutation.

        class InvoiceSerializer(serializers.ModelSerializer):
            pdf = ProtectedFileSerializerField()  # the field named like the serializer field
    """

    def __init__(
        self, field_name: Optional[str] = None, *, key: Optional[str] = None, **kwargs: Any
    ) -> None:
        self.protected_field_name = field_name
        self.protected_key = key
        kwargs["read_only"] = True
        kwargs.setdefault("source", "*")
        super().__init__(**kwargs)

    def get_spec(self, obj: models.Model) -> Optional[ProtectedFileSpec]:
        if self.protected_key:
            return protected_files.get(self.protected_key)
        return protected_files.get_for(obj, self.protected_field_name or self.field_name)

    def to_representation(self, obj: models.Model) -> Optional[dict[str, Any]]:
        request = self.context.get("request")
        user = getattr(request, "user", None)
        info = describe_protected_file(self.get_spec(obj), obj, user)
        return info.as_dict() if info else None
