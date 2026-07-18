from baseapp_core.plugins import BaseAppConfig, GraphQLContributor, ServicesContributor


class FilesConfig(BaseAppConfig, ServicesContributor, GraphQLContributor):
    default = True
    name = "baseapp.files"
    label = "baseapp_files"
    verbose_name = "BaseApp Files"
    default_auto_field = "django.db.models.BigAutoField"

    def register_shared_services(self, registry):
        from .services.metadata import FilesMetadataService

        registry.register(FilesMetadataService())

    def register_graphql_shared_interfaces(self, registry):
        from .graphql.interfaces import get_files_interface

        registry.register("FilesInterface", get_files_interface)
