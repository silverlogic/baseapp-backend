from baseapp_core.plugins import BaseAppConfig, GraphQLContributor, ServicesContributor


class PackageConfig(BaseAppConfig, ServicesContributor, GraphQLContributor):
    default = True
    name = "baseapp_mentions"
    label = "baseapp_mentions"
    verbose_name = "BaseApp Mentions"
    default_auto_field = "django.db.models.BigAutoField"

    def register_shared_services(self, registry) -> None:
        from .services import MentionableMetadataService, MentionsService

        registry.register(MentionsService())
        registry.register(MentionableMetadataService())

    def register_graphql_shared_interfaces(self, registry) -> None:
        from .graphql.shared_interfaces import get_mentions_interface

        registry.register("MentionsInterface", get_mentions_interface)
