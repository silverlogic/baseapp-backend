from django.apps import AppConfig


class PackageConfig(AppConfig):
    default = True
    name = "baseapp_core"
    label = "baseapp_core"
    verbose_name = "BaseApp Core"
    default_auto_field = "django.db.models.BigAutoField"
