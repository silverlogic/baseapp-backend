from django.utils.translation import gettext_lazy as _

from baseapp_core.plugins import BaseAppConfig


class ReferralsConfig(BaseAppConfig):
    default = True
    name = "baseapp_referrals"
    label = "baseapp_referrals"
    verbose_name = _("BaseApp Referrals")
    default_auto_field = "django.db.models.BigAutoField"
