import pytest

from baseapp_core.plugins.shared_services import (
    SharedServiceProvider,
    SharedServiceRegistry,
)


class MockSharedServiceProvider:
    """Mock service provider for testing."""

    def __init__(self, service_name: str, available: bool = True):
        self._service_name = service_name
        self._available = available

    @property
    def service_name(self) -> str:
        return self._service_name

    def is_available(self) -> bool:
        return self._available


class TestSharedServiceRegistry:
    """Test suite for SharedServiceRegistry."""

    def test_registry_initialization(self):
        """Test that registry initializes with empty state."""
        registry = SharedServiceRegistry()
        assert len(registry._registry) == 0

    def test_register_service(self):
        registry = SharedServiceRegistry()
        provider = MockSharedServiceProvider("test_service")

        registry.register("test_service", provider)
        assert "test_service" in registry._registry
        assert registry._registry["test_service"] == provider

    def test_register_non_provider_raises_typeerror(self):
        registry = SharedServiceRegistry()

        with pytest.raises(TypeError, match="Provider must implement SharedServiceProvider"):
            registry.register("test_service", "not_a_provider")

    def test_get_service_returns_provider_when_available(self):
        registry = SharedServiceRegistry()
        provider = MockSharedServiceProvider("test_service", available=True)
        registry.register("test_service", provider)

        result = registry.get("test_service")
        assert result == provider

    def test_get_service_returns_none_when_unavailable(self):
        registry = SharedServiceRegistry()
        provider = MockSharedServiceProvider("test_service", available=False)
        registry.register("test_service", provider)

        result = registry.get("test_service")
        assert result is None

    def test_get_service_returns_none_when_not_registered(self):
        registry = SharedServiceRegistry()

        result = registry.get("nonexistent_service")
        assert result is None

    def test_has_service_returns_true_when_available(self):
        registry = SharedServiceRegistry()
        provider = MockSharedServiceProvider("test_service", available=True)
        registry.register("test_service", provider)

        assert registry.has_service("test_service") is True

    def test_has_service_returns_false_when_unavailable(self):
        registry = SharedServiceRegistry()
        provider = MockSharedServiceProvider("test_service", available=False)
        registry.register("test_service", provider)

        assert registry.has_service("test_service") is False

    def test_has_service_returns_false_when_not_registered(self):
        registry = SharedServiceRegistry()

        assert registry.has_service("nonexistent_service") is False

    def test_multiple_services_registration(self):
        registry = SharedServiceRegistry()
        provider1 = MockSharedServiceProvider("service1")
        provider2 = MockSharedServiceProvider("service2")

        registry.register("service1", provider1)
        registry.register("service2", provider2)

        assert registry.has_service("service1") is True
        assert registry.has_service("service2") is True
        assert registry.get("service1") == provider1
        assert registry.get("service2") == provider2

    def test_service_overwrite(self):
        """Test that registering a service with existing name overwrites it."""
        registry = SharedServiceRegistry()
        provider1 = MockSharedServiceProvider("test_service")
        provider2 = MockSharedServiceProvider("test_service")

        registry.register("test_service", provider1)
        assert registry.get("test_service") == provider1

        registry.register("test_service", provider2)
        assert registry.get("test_service") == provider2

    def test_service_provider_protocol(self):
        """Test that SharedServiceProvider protocol is correctly implemented."""
        # MockSharedServiceProvider should satisfy the protocol
        provider = MockSharedServiceProvider("test")
        assert isinstance(provider, SharedServiceProvider)
        assert hasattr(provider, "service_name")
        assert hasattr(provider, "is_available")
        assert callable(provider.is_available)


class TestSharedServiceRegistrySingleton:
    """Test suite for the shared_services singleton."""

    def test_singleton_instance(self):
        """Test that shared_services is a singleton instance."""
        from baseapp_core.plugins.shared_services import shared_services

        assert isinstance(shared_services, SharedServiceRegistry)

    def test_singleton_persistence(self):
        """Test that the singleton persists across imports."""
        from baseapp_core.plugins.shared_services import shared_services as registry1
        from baseapp_core.plugins.shared_services import shared_services as registry2

        assert registry1 is registry2
