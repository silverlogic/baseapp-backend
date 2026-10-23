from django.db.models.signals import post_migrate
from django.utils.translation import gettext_lazy as _

from baseapp_core.plugins import BaseAppConfig


def sync_registered_email_templates(sender, using="default", apps=None, **kwargs) -> None:
    """Create blank ``EmailTemplate`` rows for registered templates after ``migrate``."""
    from .registry import sync_email_templates

    try:
        model = (apps or sender.apps).get_model("baseapp_message_templates", "EmailTemplate")
    except LookupError:  # migrated backwards past the model
        return
    sync_email_templates(using=using, model=model)


class PackageConfig(BaseAppConfig):
    default = True
    name = "baseapp_message_templates"
    label = "baseapp_message_templates"
    verbose_name = _("BaseApp Message Templates")
    default_auto_field = "django.db.models.AutoField"

    def ready(self) -> None:
        super().ready()
        post_migrate.connect(
            sync_registered_email_templates,
            sender=self,
            dispatch_uid="baseapp_message_templates.sync_registered_email_templates",
        )
