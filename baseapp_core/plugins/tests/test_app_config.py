import baseapp_core

from baseapp_core.plugins.app_config import (
    BaseAppConfig,
    GraphQLContributor,
    ServicesContributor,
)
from baseapp_core.plugins.shared_graphql_interfaces import (
    GraphQLSharedInterfaceRegistry,
)
from baseapp_core.plugins.shared_services import SharedServiceRegistry


class TestServicesContributor:
    """Test suite for ServicesContributor mixin."""

    def test_register_shared_services_default_no_op(self):
        """Default register_shared_services does nothing and does not raise."""
        registry = SharedServiceRegistry()
        contributor = ServicesContributor()
        contributor.register_shared_services(registry)
        assert len(registry._registry) == 0

    def test_register_shared_services_accepts_registry(self):
        """register_shared_services accepts a SharedServiceRegistry instance."""
        registry = SharedServiceRegistry()
        contributor = ServicesContributor()
        contributor.register_shared_services(registry)
        # No exception; registry unchanged
        assert registry.get_service("any") is None


class TestGraphQLContributor:
    """Test suite for GraphQLContributor mixin."""

    def test_register_graphql_shared_interfaces_default_no_op(self):
        """Default register_graphql_shared_interfaces does nothing and does not raise."""
        registry = GraphQLSharedInterfaceRegistry()
        contributor = GraphQLContributor()
        contributor.register_graphql_shared_interfaces(registry)
        assert len(registry._registry) == 0

    def test_register_graphql_shared_interfaces_accepts_registry(self):
        """register_graphql_shared_interfaces accepts a GraphQLSharedInterfaceRegistry."""
        registry = GraphQLSharedInterfaceRegistry()
        contributor = GraphQLContributor()
        contributor.register_graphql_shared_interfaces(registry)
        assert registry.get_interface("any") is None


class RecordingAppConfig(BaseAppConfig, ServicesContributor, GraphQLContributor):
    """AppConfig that records which register methods were called and with which registry."""

    def __init__(self, app_name: str, app_module):
        super().__init__(app_name, app_module)
        self.recorded: list[tuple[str, object]] = []

    def register_shared_services(self, registry: SharedServiceRegistry) -> None:
        self.recorded.append(("register_shared_services", registry))

    def register_graphql_shared_interfaces(self, registry: GraphQLSharedInterfaceRegistry) -> None:
        self.recorded.append(("register_graphql_shared_interfaces", registry))


class TestBaseAppConfig:
    """Test suite for BaseAppConfig ready() integration."""

    def test_ready_calls_register_shared_services_when_services_contributor(self):
        """ready() calls register_shared_services with shared_service_registry when config is ServicesContributor."""
        config = RecordingAppConfig("baseapp_core", baseapp_core)
        config.ready()
        services_calls = [r for r in config.recorded if r[0] == "register_shared_services"]
        assert len(services_calls) == 1
        assert isinstance(services_calls[0][1], SharedServiceRegistry)

    def test_ready_calls_register_graphql_shared_interfaces_when_graphql_contributor(self):
        """ready() calls register_graphql_shared_interfaces with registry when config is GraphQLContributor."""
        config = RecordingAppConfig("baseapp_core", baseapp_core)
        config.ready()
        graphql_calls = [r for r in config.recorded if r[0] == "register_graphql_shared_interfaces"]
        assert len(graphql_calls) == 1
        assert isinstance(graphql_calls[0][1], GraphQLSharedInterfaceRegistry)

    def test_ready_calls_both_when_both_mixins(self):
        """ready() calls both register methods when config has both mixins."""
        config = RecordingAppConfig("baseapp_core", baseapp_core)
        config.ready()
        assert len(config.recorded) == 2
        assert config.recorded[0][0] == "register_shared_services"
        assert config.recorded[1][0] == "register_graphql_shared_interfaces"
