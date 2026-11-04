import typing

import pytest
from drf_spectacular.generators import SchemaGenerator
from rest_framework import serializers as drf_serializers

from baseapp_payments import serializers as payments_serializers


def _method_field_getters() -> list:
    getters = []
    for serializer_class in vars(payments_serializers).values():
        if not (
            isinstance(serializer_class, type)
            and issubclass(serializer_class, drf_serializers.Serializer)
            and serializer_class.__module__ == payments_serializers.__name__
        ):
            continue
        for name, field in serializer_class._declared_fields.items():
            if isinstance(field, drf_serializers.SerializerMethodField):
                getters.append(getattr(serializer_class, field.method_name or f"get_{name}"))
    return getters


@pytest.mark.parametrize("getter", _method_field_getters(), ids=lambda g: g.__qualname__)
def test_serializer_method_field_type_hints_resolve(getter: typing.Callable) -> None:
    """drf-spectacular reads these hints at runtime; a TYPE_CHECKING-only name is a NameError."""
    typing.get_type_hints(getter)


def test_openapi_schema_generates() -> None:
    """Regression for BASEAPP-BACKEND-TEMPLATE-GA: /api/schema/ 500'd on the payments serializers."""
    # Same api_version the templates' SpectacularAPIView passes; without it the
    # versioned v1 views are skipped and nothing gets inspected.
    schema = SchemaGenerator(api_version="v1").get_schema(request=None, public=True)

    assert any("payments" in path for path in schema["paths"])
