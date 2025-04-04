import swapper
from django.conf import settings


def use_referrals():
    return "baseapp_referrals" in settings.INSTALLED_APPS


def get_user_referral_model():
    if use_referrals():
        return swapper.load_model("baseapp_referrals", "UserReferral", required=False)
    else:
        return None
