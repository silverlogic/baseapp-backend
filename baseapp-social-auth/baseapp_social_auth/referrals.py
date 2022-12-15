from django.contrib.auth import get_user_model
from django.db.models import ObjectDoesNotExist
from hashids import Hashids

hashids = Hashids(salt="referral-codes", min_length=4)


def get_referral_code(user):
    return hashids.encode(user.pk)


def get_user_from_referral_code(referral_code):
    """Returns the user related to the referral code or None."""
    pk = hashids.decode(referral_code)
    if pk:
        pk = pk[0]
    else:
        return None
    try:
        return get_user_model().objects.get(pk=pk)
    except ObjectDoesNotExist:
        return None
