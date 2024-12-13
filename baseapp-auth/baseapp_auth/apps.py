from allauth.account.signals import email_confirmed
from django.apps import AppConfig

from .settings import JWT_CLAIM_SERIALIZER_CLASS, SIMPLE_JWT


class AuthConfig(AppConfig):
    default = True
    name = "baseapp_auth"
    verbose_name = "BaseApp Auth"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        from django.conf import settings  # noqa

        from .extensions.allauth.account.signals import on_email_confirmed

        # Set default settings
        settings.SIMPLE_JWT = {
            **SIMPLE_JWT,
            **getattr(settings, "SIMPLE_JWT", {}),
        }
        settings.JWT_CLAIM_SERIALIZER_CLASS = getattr(
            settings, "JWT_CLAIM_SERIALIZER_CLASS", JWT_CLAIM_SERIALIZER_CLASS
        )

        # Set up signal to send welcome email to new users
        email_confirmed.connect(on_email_confirmed)
