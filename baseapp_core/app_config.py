"""
Runtime extension contract for plugin apps.

BaseAppConfig is the single integration point for runtime registration.
Apps that provide services or GraphQL capabilities use the optional mixins
and register in ready(). All wiring happens in AppConfig.ready() for
load-order safety and to avoid import-time side effects.
"""

from typing import TYPE_CHECKING

from django.apps import AppConfig

if TYPE_CHECKING:
    from baseapp_core.graphql.interfaces import GraphQLSharedInterfaceRegistry
    from baseapp_core.services.registry import SharedServiceRegistry


class ServicesContributor:
    """
    Mixin for AppConfig: register services at runtime in ready().

    Override register_shared_services() and call the registry for each service
    your app provides. Consumers resolve services lazily via the
    service registry; no direct imports between apps.
    """

    def register_shared_services(self, registry: "SharedServiceRegistry") -> None:
        """
        Register this app's shared services with the runtime service registry.

        Override in your app and call shared_service_registry.register(name, instance)
        for each shared service you provide.
        """
        pass


class GraphQLContributor:
    """
    Mixin for AppConfig: register GraphQL shared interfaces at runtime in ready().

    Override register_graphql_shared_interfaces() and call the shared interface registry
    for each named shared interface your app provides. Consumers explicitly
    opt in by name when defining their GraphQL types.
    """

    def register_graphql_shared_interfaces(
        self, registry: "GraphQLSharedInterfaceRegistry"
    ) -> None:
        """
        Register this app's GraphQL shared interfaces with the runtime registry.

        Override in your app and call graphql_shared_interface_registry.register(name, interface)
        for each shared interface you provide. Shared interfaces are app-agnostic; consumers
        opt in by name.
        """
        pass


class BaseAppConfig(AppConfig):
    """
    Base app config for plugin apps. Use with ServicesContributor and/or
    GraphQLContributor mixins to expose runtime behavior. All registration
    happens in ready(); no entry points for hooks, services, or GraphQL.
    """

    def ready(self) -> None:
        """Run runtime registration: services and GraphQL capabilities."""
        from baseapp_core.graphql.interfaces import graphql_shared_interface_registry
        from baseapp_core.services.registry import shared_service_registry

        if isinstance(self, ServicesContributor):
            self.register_shared_services(shared_service_registry)
        if isinstance(self, GraphQLContributor):
            self.register_graphql_shared_interfaces(graphql_shared_interface_registry)
