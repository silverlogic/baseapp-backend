from baseapp_core.plugins import BaseAppConfig, GraphQLContributor, ServicesContributor


class PackageConfig(BaseAppConfig, ServicesContributor, GraphQLContributor):
    default = True
    name = "baseapp_reactions"
    label = "baseapp_reactions"
    verbose_name = "BaseApp Reactions"
    default_auto_field = "django.db.models.AutoField"

    def ready(self) -> None:
        super().ready()
        import baseapp_reactions.signals  # noqa

    def register_shared_services(self, registry) -> None:
        from .services import ReactableMetadataService

        registry.register(ReactableMetadataService())

    def register_graphql_shared_interfaces(self, registry) -> None:
        from .graphql.interfaces import get_reactions_interface

        registry.register("ReactionsInterface", get_reactions_interface)
