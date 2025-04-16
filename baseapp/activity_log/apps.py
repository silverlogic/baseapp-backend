from django.apps import AppConfig


class PackageConfig(AppConfig):
    default = True
    name = "baseapp.activity_log"
    label = "baseapp_activity_log"
    verbose_name = "BaseApp Activity Log"
    default_auto_field = "django.db.models.BigAutoField"
