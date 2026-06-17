from baseapp_core.plugins import BaseAppConfig, GraphQLContributor, ServicesContributor


class PackageConfig(BaseAppConfig, ServicesContributor, GraphQLContributor):
    default = True
    name = "baseapp_reports"
    label = "baseapp_reports"
    verbose_name = "BaseApp Reports"
    default_auto_field = "django.db.models.AutoField"

    def register_shared_services(self, registry):
        from .services import ReportableMetadataService

        registry.register(ReportableMetadataService())

    def register_graphql_shared_interfaces(self, registry):
        from .graphql.interfaces import get_reports_interface

        registry.register("ReportsInterface", get_reports_interface)
