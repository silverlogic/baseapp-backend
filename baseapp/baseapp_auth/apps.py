from django.apps import AppConfig

from .settings import JWT_CLAIM_SERIALIZER_CLASS, SIMPLE_JWT


class PackageConfig(AppConfig):
    default = True
    name = "baseapp_auth"
    label = "baseapp_auth"
    verbose_name = "BaseApp Auth"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        from django.conf import settings  # noqa

        # Set default settings
        settings.SIMPLE_JWT = {
            **SIMPLE_JWT,
            **getattr(settings, "SIMPLE_JWT", {}),
        }
        settings.JWT_CLAIM_SERIALIZER_CLASS = getattr(
            settings, "JWT_CLAIM_SERIALIZER_CLASS", JWT_CLAIM_SERIALIZER_CLASS
        )
