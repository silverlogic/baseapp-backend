from baseapp_core.plugins import BaseAppConfig


class PackageConfig(BaseAppConfig):
    default = True
    name = "baseapp_e2e"
    label = "baseapp_e2e"
    verbose_name = "BaseApp E2e"
    default_auto_field = "django.db.models.BigAutoField"
