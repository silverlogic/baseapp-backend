from django.apps import AppConfig


class PackageConfig(AppConfig):
    default = True
    name = "baseapp_reports"
    label = "baseapp_reports"
    verbose_name = "BaseApp Reports"
    default_auto_field = "django.db.models.AutoField"
