import pytest
from django.contrib.auth import get_user_model

from baseapp_referrals.utils import get_referral_code, get_user_from_referral_code

pytestmark = pytest.mark.django_db


def test_round_trip_referral_code():
    user = get_user_model().objects.create()
    assert get_user_from_referral_code(get_referral_code(user)) == user


def test_get_user_when_referral_code_is_invalid():
    assert get_user_from_referral_code("18239asdf") is None


def test_get_user_when_user_does_not_exist():
    user = get_user_model().objects.create()
    referral_code = get_referral_code(user)
    user.delete()
    assert get_user_from_referral_code(referral_code) is None
