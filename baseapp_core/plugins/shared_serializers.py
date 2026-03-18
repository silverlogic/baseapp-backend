"""
Runtime serializer registry. Serializers are registered in AppConfig.ready();
consumers resolve serializer classes lazily by name.
"""

import inspect
from typing import Any, Callable

from rest_framework import serializers

from .readiness import require_django_ready

SerializerValue = type[serializers.BaseSerializer] | Callable[[], type[serializers.BaseSerializer]]


class SharedSerializerRegistry:
    """
    Runtime-only registry for reusable serializer classes.
    """

    def __init__(self) -> None:
        self._registry: dict[str, SerializerValue] = {}

    def register(self, name: str, serializer: SerializerValue) -> None:
        """Register a serializer by name. Call from AppConfig.ready()."""
        self._registry[name] = serializer

    @require_django_ready
    def get_serializer(self, name: str) -> type[serializers.BaseSerializer] | None:
        """Resolve and return the serializer class for name, or None if not registered."""
        value = self._registry.get(name)
        if value is None:
            return None
        if inspect.isclass(value) and issubclass(value, serializers.BaseSerializer):
            return value
        if callable(value):
            return value()
        return value

    @require_django_ready
    def serialize(
        self,
        name: str,
        instance: Any,
        *,
        context: dict[str, Any] | None = None,
        many: bool = False,
        default: Any = None,
    ) -> Any:
        """
        Serialize instance with the named serializer, or return default if unavailable.
        """
        serializer_class = self.get_serializer(name)
        if serializer_class is None or instance is None:
            return default
        return serializer_class(instance=instance, context=context or {}, many=many).data


shared_serializer_registry = SharedSerializerRegistry()
