from django.apps import AppConfig


class PackageConfig(AppConfig):
    name = "baseapp.reports"
    label = "baseapp_reports"
    verbose_name = "BaseApp Reports"
    default_auto_field = "django.db.models.BigAutoField"
