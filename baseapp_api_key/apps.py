from django.apps import AppConfig


class PackageConfig(AppConfig):
    default = True
    name = "baseapp_api_key"
    label = "baseapp_api_key"
    verbose_name = "BaseApp API Key"
    default_auto_field = "django.db.models.AutoField"
