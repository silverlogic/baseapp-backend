from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class PackageConfig(AppConfig):
    default = True
    name = "baseapp_wagtail"
    label = "baseapp_wagtail"
    verbose_name = _("BaseApp Wagtail")
    default_auto_field = "django.db.models.BigAutoField"
