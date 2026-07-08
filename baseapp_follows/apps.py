from baseapp_core.plugins import (
    BaseAppConfig,
    GraphQLContributor,
    GraphQLSharedInterfaceRegistry,
    ServicesContributor,
)


class PackageConfig(BaseAppConfig, ServicesContributor, GraphQLContributor):
    default = True
    name = "baseapp_follows"
    label = "baseapp_follows"
    verbose_name = "BaseApp Follows"
    default_auto_field = "django.db.models.AutoField"

    def register_shared_services(self, registry):
        from .services import FollowableMetadataService

        registry.register(FollowableMetadataService())

    def register_graphql_shared_interfaces(self, registry: GraphQLSharedInterfaceRegistry):
        from .graphql.interfaces import FollowsInterface

        registry.register("FollowsInterface", FollowsInterface)
