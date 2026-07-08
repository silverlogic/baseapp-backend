from baseapp_core.plugins import BaseAppConfig, GraphQLContributor, ServicesContributor


class PackageConfig(BaseAppConfig, ServicesContributor, GraphQLContributor):
    default = True
    name = "baseapp_ratings"
    label = "baseapp_ratings"
    verbose_name = "BaseApp Ratings"
    default_auto_field = "django.db.models.AutoField"

    def register_shared_services(self, registry):
        from .services import RatableMetadataService

        registry.register(RatableMetadataService())

    def register_graphql_shared_interfaces(self, registry):
        from .graphql.interfaces import get_ratings_interface

        registry.register("RatingsInterface", get_ratings_interface)
