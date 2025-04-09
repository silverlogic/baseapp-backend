from django.apps import AppConfig


class PackageConfig(AppConfig):
    default = True
    name = "baseapp_profiles"
    label = "baseapp_profiles"
    verbose_name = "BaseApp Profiles"
    default_auto_field = "django.db.models.AutoField"
