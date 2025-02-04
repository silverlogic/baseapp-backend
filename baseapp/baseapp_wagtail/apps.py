from django.apps import AppConfig


class WagtailConfig(AppConfig):
    default = True
    name = "baseapp_wagtail"
    verbose_name = "BaseApp Wagtail"
    default_auto_field = "django.db.models.BigAutoField"
