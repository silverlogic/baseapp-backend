"""
Runtime GraphQL shared-interface registry. Providers register a getter in AppConfig.ready();
consumers opt in by name when defining their Strawberry types.
"""

import inspect
from typing import Any, Callable

from .readiness import require_django_ready


class GraphQLSharedInterfaceRegistry:
    """Name -> interface getter (or class). Consumers assemble interfaces explicitly."""

    def __init__(self) -> None:
        self._registry: dict[str, Any] = {}

    def register(self, name: str, interface: type | Callable[[], Any]) -> None:
        """Register a shared interface by name. Call from AppConfig.ready()."""
        self._registry[name] = interface

    @require_django_ready
    def get_interface(self, name: str) -> Any:
        """The interface registered as `name` (a getter is called), or None."""
        value = self._registry.get(name)
        if value is None or inspect.isclass(value):
            return value
        return value() if callable(value) else value

    @require_django_ready
    def get(self, *interfaces: str | type) -> tuple:
        """Interfaces for registered names or classes; unregistered names are skipped."""
        result = []
        for name_or_class in interfaces:
            if isinstance(name_or_class, str):
                iface = self.get_interface(name_or_class)
            elif inspect.isclass(name_or_class):
                iface = name_or_class
            else:
                raise TypeError(
                    f"Invalid interface type: {name_or_class} of type {type(name_or_class)}"
                )
            if iface is not None:
                result.extend(iface if isinstance(iface, list) else [iface])
        return tuple(result)


# Strawberry interfaces register a getter function, never the class itself.
strawberry_shared_interfaces = GraphQLSharedInterfaceRegistry()
