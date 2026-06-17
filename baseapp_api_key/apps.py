from baseapp_core.plugins import BaseAppConfig


class PackageConfig(BaseAppConfig):
    default = True
    name = "baseapp_api_key"
    label = "baseapp_api_key"
    verbose_name = "BaseApp API Key"
    default_auto_field = "django.db.models.AutoField"
