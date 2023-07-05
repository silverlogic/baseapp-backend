from .models import UserReferral
from .utils import get_user_from_referral_code


def link_user_to_referrer(is_new, strategy, user, *args, **kwargs):
    if not is_new:
        return

    if strategy.request.data.get("referral_code"):
        referrer = get_user_from_referral_code(strategy.request.data["referral_code"])
        UserReferral.objects.create(referrer=referrer, referee=user)
