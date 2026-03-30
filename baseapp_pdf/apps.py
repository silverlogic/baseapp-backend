from baseapp_core.plugins import BaseAppConfig


class PackageConfig(BaseAppConfig):
    default = True
    name = "baseapp_pdf"
    label = "baseapp_pdf"
    verbose_name = "BaseApp PDF"
    default_auto_field = "django.db.models.AutoField"
