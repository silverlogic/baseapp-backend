"""
Runtime shared service registry. Shared services are registered in AppConfig.ready();
no entry points. Consumers resolve shared services lazily via get_service().
"""

from typing import Optional, Protocol, runtime_checkable


@runtime_checkable
class ServiceProvider(Protocol):
    """Protocol for objects that provide a named service."""

    @property
    def service_name(self) -> str: ...  # noqa: E704

    def is_available(self) -> bool: ...  # noqa: E704


class SharedServiceRegistry:
    """
    Runtime-only registry. Providers register in ready() via register().
    Missing shared services are handled gracefully (get_service returns None).
    """

    def __init__(self) -> None:
        self._registry: dict[str, ServiceProvider] = {}

    def register(self, service_name: str, provider: ServiceProvider) -> None:
        """Register a shared service. Call from AppConfig.ready() (e.g. in register_shared_services())."""
        if not isinstance(provider, ServiceProvider):
            raise TypeError(f"Provider must implement ServiceProvider protocol: {type(provider)}")
        self._registry[service_name] = provider

    def get_service(self, service_name: str) -> Optional[ServiceProvider]:
        """Return the provider for service_name, or None if missing/unavailable."""
        provider = self._registry.get(service_name)
        if provider is None:
            return None
        if not provider.is_available():
            return None
        return provider

    def has_service(self, service_name: str) -> bool:
        """Return True if a registered, available service exists for service_name."""
        return self.get_service(service_name) is not None


shared_service_registry = SharedServiceRegistry()
