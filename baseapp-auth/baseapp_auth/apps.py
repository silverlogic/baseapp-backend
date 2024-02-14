from django.apps import AppConfig


class AuthConfig(AppConfig):
    default = True
    name = "baseapp_auth"
    verbose_name = "BaseApp Auth"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        pass
