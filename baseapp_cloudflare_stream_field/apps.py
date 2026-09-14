from django.utils.translation import gettext_lazy as _

from baseapp_core.plugins import BaseAppConfig


class PackageConfig(BaseAppConfig):
    default = True
    name = "baseapp_cloudflare_stream_field"
    label = "baseapp_cloudflare_stream_field"
    verbose_name = _("BaseApp Cloudflare Stream Field")
    default_auto_field = "django.db.models.AutoField"
