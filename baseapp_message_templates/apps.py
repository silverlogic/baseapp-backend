from baseapp_core.plugins import BaseAppConfig


class PackageConfig(BaseAppConfig):
    default = True
    name = "baseapp_message_templates"
    label = "baseapp_message_templates"
    verbose_name = "BaseApp Message Templates"
    default_auto_field = "django.db.models.AutoField"
