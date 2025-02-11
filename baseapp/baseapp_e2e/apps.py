from django.apps import AppConfig


class PackageConfig(AppConfig):
    default = True
    name = "baseapp_e2e"
    label = "baseapp_e2e"
    verbose_name = "BaseApp E2e"
    default_auto_field = "django.db.models.BigAutoField"
