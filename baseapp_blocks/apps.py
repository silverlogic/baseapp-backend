from baseapp_core.plugins import BaseAppConfig, GraphQLContributor, ServicesContributor


class PackageConfig(BaseAppConfig, ServicesContributor, GraphQLContributor):
    default = True
    name = "baseapp_blocks"
    label = "baseapp_blocks"
    verbose_name = "BaseApp Blocks"
    default_auto_field = "django.db.models.AutoField"

    def register_shared_services(self, registry) -> None:
        from .services import BlockableMetadataService, BlockLookupService

        registry.register(BlockLookupService())
        registry.register(BlockableMetadataService())

    def register_graphql_shared_interfaces(self, registry) -> None:
        from .graphql.interfaces import get_blocks_interface

        registry.register("BlocksInterface", get_blocks_interface)
