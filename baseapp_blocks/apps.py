from django.apps import AppConfig


class PackageConfig(AppConfig):
    default = True
    name = "baseapp_blocks"
    label = "baseapp_blocks"
    verbose_name = "BaseApp Blocks"
    default_auto_field = "django.db.models.AutoField"
