from baseapp_core.plugins import BaseAppConfig, ServicesContributor


class PackageConfig(BaseAppConfig, ServicesContributor):
    default = True
    name = "baseapp_organizations"
    label = "baseapp_organizations"
    verbose_name = "BaseApp Organizations"
    default_auto_field = "django.db.models.AutoField"

    def register_shared_services(self, registry) -> None:
        from .services import OrganizationAccountService

        registry.register(OrganizationAccountService())
