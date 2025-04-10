from django.apps import AppConfig


class PackageConfig(AppConfig):
    default = True
    name = "baseapp_wagtail"
    label = "baseapp_wagtail"
    verbose_name = "BaseApp Wagtail"
    default_auto_field = "django.db.models.BigAutoField"
