from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class WagtailConfig(AppConfig):
    name = "baseapp_wagtail.medias"
    verbose_name = _("BaseApp Wagtail - Medias")
    label = "baseapp_wagtail_medias"
