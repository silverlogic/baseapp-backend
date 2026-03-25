from baseapp_core.plugins import BaseAppConfig, GraphQLContributor, ServicesContributor


class PackageConfig(BaseAppConfig, GraphQLContributor, ServicesContributor):
    default = True
    name = "baseapp_pages"
    label = "baseapp_pages"
    verbose_name = "BaseApp Pages"
    default_auto_field = "django.db.models.AutoField"

    def register_shared_services(self, registry):
        from .services import URLPathService

        registry.register(URLPathService())

    def register_graphql_shared_interfaces(self, registry):
        from .graphql.interfaces import get_page_interface

        registry.register("PageInterface", get_page_interface)
