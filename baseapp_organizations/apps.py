from django.apps import AppConfig


class PackageConfig(AppConfig):
    default = True
    name = "baseapp_organizations"
    label = "baseapp_organizations"
    verbose_name = "BaseApp Organizations"
    default_auto_field = "django.db.models.AutoField"
