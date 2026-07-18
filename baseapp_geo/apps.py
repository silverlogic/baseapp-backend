from django.utils.translation import gettext_lazy as _

from baseapp_core.plugins import BaseAppConfig


class BaseappGeoConfig(BaseAppConfig):
    default = True
    name = "baseapp_geo"
    label = "baseapp_geo"
    verbose_name = _("BaseApp Geo")
    default_auto_field = "django.db.models.AutoField"
