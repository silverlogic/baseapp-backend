from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class WagtailConfig(AppConfig):
    name = "baseapp_wagtail.base"
    verbose_name = _("BaseApp Wagtail - Base")
    label = "baseapp_wagtail_base"
