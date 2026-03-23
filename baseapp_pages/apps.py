from baseapp_core.plugins import BaseAppConfig, GraphQLContributor


class PackageConfig(BaseAppConfig, GraphQLContributor):
    name = "baseapp_pages"
    label = "baseapp_pages"
    verbose_name = "BaseApp Pages"
    default_auto_field = "django.db.models.AutoField"

    def register_graphql_shared_interfaces(self, registry):
        from .graphql.interfaces import get_pages_interface

        registry.register("PageInterface", get_pages_interface)
