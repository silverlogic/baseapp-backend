from django.apps import AppConfig


class PackageConfig(AppConfig):
    default = True
    name = "baseapp_notifications"
    label = "baseapp_notifications"
    verbose_name = "BaseApp Notifications"
    default_auto_field = "django.db.models.AutoField"
