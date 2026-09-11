from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class PluginTestAppConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "testproject.plugin_test_app"
    verbose_name = _("Plugin Test App")
