from django.apps import AppConfig


class PluginTestAppConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "testproject.plugin_test_app"
    verbose_name = "Plugin Test App"
