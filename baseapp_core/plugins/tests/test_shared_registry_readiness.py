import pytest
from django.apps import apps
from django.core.exceptions import ImproperlyConfigured

from baseapp_core.plugins.shared_graphql_interfaces import (
    GraphQLSharedInterfaceRegistry,
)
from baseapp_core.plugins.shared_serializers import SharedSerializerRegistry
from baseapp_core.plugins.shared_services import SharedServiceRegistry


@pytest.mark.parametrize(
    ("callback", "accessor_name"),
    [
        (
            lambda registry: registry.get_interface("test_interface"),
            "GraphQLSharedInterfaceRegistry.get_interface()",
        ),
        (
            lambda registry: registry.get_serializer("test_serializer"),
            "SharedSerializerRegistry.get_serializer()",
        ),
        (
            lambda registry: registry.get("test_service"),
            "SharedServiceRegistry.get()",
        ),
    ],
)
def test_shared_registry_getters_raise_before_django_ready(
    monkeypatch: pytest.MonkeyPatch,
    callback,
    accessor_name: str,
):
    monkeypatch.setattr(apps, "ready", False)

    registry_map = {
        "GraphQLSharedInterfaceRegistry.get_interface()": GraphQLSharedInterfaceRegistry(),
        "SharedSerializerRegistry.get_serializer()": SharedSerializerRegistry(),
        "SharedServiceRegistry.get()": SharedServiceRegistry(),
    }
    registry = registry_map[accessor_name]

    with pytest.raises(ImproperlyConfigured) as exc:
        callback(registry)

    message = str(exc.value)
    assert accessor_name in message
    assert "Most likely reason" in message
    assert "Backtrace:" in message
