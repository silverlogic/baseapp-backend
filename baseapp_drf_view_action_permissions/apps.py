from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class PackageConfig(AppConfig):
    default = True
    name = "baseapp_drf_view_action_permissions"
    label = "baseapp_drf_view_action_permissions"
    verbose_name = _("BaseApp DRF View Action Permissions")
    default_auto_field = "django.db.models.AutoField"
