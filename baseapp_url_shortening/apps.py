from django.utils.translation import gettext_lazy as _

from baseapp_core.plugins import BaseAppConfig


class PackageConfig(BaseAppConfig):
    default = True
    name = "baseapp_url_shortening"
    label = "baseapp_url_shortening"
    verbose_name = _("BaseApp URL Shortening")
    default_auto_field = "django.db.models.AutoField"
