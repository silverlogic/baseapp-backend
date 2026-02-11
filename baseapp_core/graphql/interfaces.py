"""
Runtime GraphQL capability registry. Capabilities are registered in
AppConfig.ready(); no entry points. Consumers opt in by name when
defining GraphQL object types.
"""

from typing import Any, Callable, List, Optional, Union

from graphene import Interface

# Lazy/callable that returns an interface class
CapabilityValue = Union[Interface, Callable[[], Any]]


class GraphQLSharedInterfaceRegistry:
    """
    Runtime-only registry. Providers register in ready() via register().
    Consumers call get_interface(name) or get_interfaces(names, default_interfaces).
    No schema mutation by side effect; consumers assemble interfaces explicitly.
    """

    def __init__(self) -> None:
        self._registry: dict[str, CapabilityValue] = {}

    def register(self, name: str, interface: CapabilityValue) -> None:
        """Register a GraphQL capability by name. Call from AppConfig.ready()."""
        self._registry[name] = interface

    def get_interface(self, name: str) -> Optional[Any]:
        """Resolve and return the interface for name, or None if not registered."""
        value = self._registry.get(name)
        if value is None:
            return None
        if callable(value) and not isinstance(value, Interface):
            return value()
        return value

    def get_interfaces(
        self,
        interface_names: List[str],
        default_interfaces: Optional[List[Any]] = None,
    ) -> tuple:
        """
        Return (default_interfaces + interfaces for the given names).
        Missing names are skipped; no error. Consumers opt in explicitly.
        """
        if default_interfaces is None:
            default_interfaces = []
        result = list(default_interfaces)
        for name in interface_names:
            iface = self.get_interface(name)
            if iface is not None:
                result.append(iface)
        return tuple(result)


graphql_shared_interface_registry = GraphQLSharedInterfaceRegistry()
