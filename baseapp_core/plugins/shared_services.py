"""
Runtime shared service registry. Shared services are registered in AppConfig.ready();
no entry points. Consumers resolve shared services lazily via get_service().
"""

from typing import Optional, Protocol, runtime_checkable


@runtime_checkable
class SharedServiceProvider(Protocol):
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
        self._registry: dict[str, SharedServiceProvider] = {}

    def register(self, provider: SharedServiceProvider) -> None:
        """Register a shared service. Call from AppConfig.ready() (e.g. in register_shared_services())."""
        if not isinstance(provider, SharedServiceProvider):
            raise TypeError(
                f"Provider must implement SharedServiceProvider protocol: {type(provider)}"
            )
        self._registry[provider.service_name] = provider

    def get_service(self, service_name: str) -> Optional[SharedServiceProvider]:
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
