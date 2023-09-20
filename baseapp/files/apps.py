from baseapp_core.plugins import BaseAppConfig, GraphQLContributor


class FilesConfig(BaseAppConfig, GraphQLContributor):
    default = True
    name = "baseapp.files"
    label = "baseapp_files"
    verbose_name = "BaseApp Files"
    default_auto_field = "django.db.models.BigAutoField"

    def register_graphql_shared_interfaces(self, registry):
        from .graphql.interfaces import get_files_interface

        registry.register("FilesInterface", get_files_interface)
