from django.apps import AppConfig


class PackageConfig(AppConfig):
    default = True
    name = "baseapp.maps"
    label = "baseapp_maps"
    verbose_name = "BaseApp Maps"
    default_auto_field = "django.db.models.BigAutoField"
