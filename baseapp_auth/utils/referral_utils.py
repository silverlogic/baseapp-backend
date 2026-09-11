from typing import TYPE_CHECKING

import swapper
from django.conf import settings

if TYPE_CHECKING:
    from django.db import models


def use_referrals() -> bool:
    return "baseapp_referrals" in settings.INSTALLED_APPS


def get_user_referral_model() -> "type[models.Model] | None":
    if use_referrals():
        return swapper.load_model("baseapp_referrals", "UserReferral", required=False)
    else:
        return None
