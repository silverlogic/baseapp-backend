from django.apps import AppConfig


class PackageConfig(AppConfig):
    default = True
    name = "baseapp_files"
    label = "baseapp_files"
    verbose_name = "BaseApp Files"
    default_auto_field = "django.db.models.BigAutoField"
