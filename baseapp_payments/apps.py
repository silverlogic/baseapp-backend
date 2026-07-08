from baseapp_core.plugins import BaseAppConfig


class PackageConfig(BaseAppConfig):
    default = True
    name = "baseapp_payments"
    label = "baseapp_payments"
    verbose_name = "BaseApp Payments"
    default_auto_field = "django.db.models.AutoField"
