from graphene import Interface, ObjectType, String

from baseapp_core.plugins import (
    GraphQLSharedInterfaceRegistry,
    graphql_shared_interfaces,
)


class MockInterface(Interface):
    """Mock GraphQL interface for testing."""

    test_field = String()


class MockObjectType(ObjectType):
    """Mock GraphQL object type for testing."""

    class Meta:
        interfaces = (MockInterface,)


class TestGraphQLSharedInterfaceRegistry:
    """Test suite for GraphQLSharedInterfaceRegistry."""

    def test_registry_initialization(self):
        """Test that registry initializes with empty state."""
        registry = GraphQLSharedInterfaceRegistry()
        assert len(registry._registry) == 0

    def test_register_interface(self):
        registry = GraphQLSharedInterfaceRegistry()
        registry.register("test_interface", MockInterface)

        assert "test_interface" in registry._registry
        assert registry._registry["test_interface"] == MockInterface

    def test_get_interface_returns_registered_interface(self):
        registry = GraphQLSharedInterfaceRegistry()
        registry.register("test_interface", MockInterface)

        result = registry.get_interface("test_interface")
        assert result == MockInterface

    def test_get_interface_returns_none_when_not_registered(self):
        registry = GraphQLSharedInterfaceRegistry()

        result = registry.get_interface("nonexistent_interface")
        assert result is None

    def test_get_interface_resolves_callable(self):
        registry = GraphQLSharedInterfaceRegistry()

        def get_interface():
            return MockInterface

        registry.register("test_interface", get_interface)

        result = registry.get_interface("test_interface")
        assert result == MockInterface

    def test_get_interfaces_returns_default_when_no_names(self):
        registry = GraphQLSharedInterfaceRegistry()
        default_interfaces = [MockInterface]

        result = registry.get_interfaces([], default_interfaces)
        assert result == tuple(default_interfaces)

    def test_get_interfaces_includes_registered_interfaces(self):
        registry = GraphQLSharedInterfaceRegistry()
        registry.register("test_interface", MockInterface)
        default_interfaces = []

        result = registry.get_interfaces(["test_interface"], default_interfaces)
        assert len(result) == 1
        assert result[0] == MockInterface

    def test_get_interfaces_combines_default_and_registered(self):
        registry = GraphQLSharedInterfaceRegistry()
        registry.register("test_interface", MockInterface)

        class DefaultInterface(Interface):
            default_field = String()

        default_interfaces = [DefaultInterface]

        result = registry.get_interfaces(["test_interface"], default_interfaces)
        assert len(result) == 2
        assert result[0] == DefaultInterface
        assert result[1] == MockInterface

    def test_get_interfaces_skips_missing_interfaces(self):
        registry = GraphQLSharedInterfaceRegistry()
        default_interfaces = []

        result = registry.get_interfaces(["nonexistent"], default_interfaces)
        assert result == tuple(default_interfaces)

    def test_get_interfaces_handles_mixed_existing_and_missing(self):
        registry = GraphQLSharedInterfaceRegistry()
        registry.register("existing", MockInterface)
        default_interfaces = []

        result = registry.get_interfaces(["existing", "missing"], default_interfaces)
        assert len(result) == 1
        assert result[0] == MockInterface

    def test_interface_overwrite(self):
        """Test that registering an interface with existing name overwrites it."""
        registry = GraphQLSharedInterfaceRegistry()

        class Interface1(Interface):
            field1 = String()

        class Interface2(Interface):
            field2 = String()

        registry.register("test_interface", Interface1)
        assert registry.get_interface("test_interface") == Interface1

        registry.register("test_interface", Interface2)
        assert registry.get_interface("test_interface") == Interface2

    def test_multiple_interfaces_registration(self):
        registry = GraphQLSharedInterfaceRegistry()

        class Interface1(Interface):
            field1 = String()

        class Interface2(Interface):
            field2 = String()

        registry.register("interface1", Interface1)
        registry.register("interface2", Interface2)

        assert registry.get_interface("interface1") == Interface1
        assert registry.get_interface("interface2") == Interface2


class TestGraphQLSharedInterfaceRegistrySingleton:
    """Test suite for the graphql_shared_interfaces singleton."""

    def test_singleton_instance(self):
        """Test that graphql_shared_interfaces is a singleton instance."""
        assert isinstance(graphql_shared_interfaces, GraphQLSharedInterfaceRegistry)

    def test_singleton_persistence(self):
        """Test that the singleton persists across imports."""
        from baseapp_core.plugins.shared_graphql_interfaces import (
            graphql_shared_interfaces as registry1,
        )
        from baseapp_core.plugins.shared_graphql_interfaces import (
            graphql_shared_interfaces as registry2,
        )

        assert registry1 is registry2
