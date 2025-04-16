from django.apps import AppConfig


class PackageConfig(AppConfig):
    default = True
    name = "baseapp_url_shortening"
    label = "baseapp_url_shortening"
    verbose_name = "BaseApp URL Shortening"
    default_auto_field = "django.db.models.AutoField"
