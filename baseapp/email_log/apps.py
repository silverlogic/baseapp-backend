from django.utils.translation import gettext_lazy as _

from baseapp_core.plugins import BaseAppConfig


class PackageConfig(BaseAppConfig):
    default = True
    name = "baseapp.email_log"
    label = "baseapp_email_log"
    verbose_name = _("BaseApp Email Log")
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        super().ready()
        from . import checks  # noqa: F401  (registers the attachment storage check)
