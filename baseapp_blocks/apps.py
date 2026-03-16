from baseapp_core.plugins import BaseAppConfig, ServicesContributor


class PackageConfig(BaseAppConfig, ServicesContributor):
    default = True
    name = "baseapp_blocks"
    label = "baseapp_blocks"
    verbose_name = "BaseApp Blocks"
    default_auto_field = "django.db.models.AutoField"

    def register_shared_services(self, registry) -> None:
        from .services import BlockLookupService

        registry.register(BlockLookupService())
