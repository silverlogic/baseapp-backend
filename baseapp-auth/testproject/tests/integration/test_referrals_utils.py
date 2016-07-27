import pytest

from apps.referrals.utils import get_referral_code, get_user_from_referral_code

import tests.factories as f

pytestmark = pytest.mark.django_db


def test_round_trip_referral_code():
    user = f.UserFactory()
    assert get_user_from_referral_code(get_referral_code(user)) == user


def test_get_user_when_referral_code_is_invalid():
    assert get_user_from_referral_code('18239asdf') is None


def test_get_user_when_user_does_not_exist():
    user = f.UserFactory()
    referral_code = get_referral_code(user)
    user.delete()
    assert get_user_from_referral_code(referral_code) is None
