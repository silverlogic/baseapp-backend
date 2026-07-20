from types import SimpleNamespace

import pytest
import swapper

from baseapp_core.tests.factories import UserFactory
from baseapp_referrals.pipeline import link_user_to_referrer
from baseapp_referrals.utils import get_referral_code

pytestmark = pytest.mark.django_db

UserReferral = swapper.load_model("baseapp_referrals", "UserReferral")


def _strategy(data) -> SimpleNamespace:
    """Minimal social-auth strategy stub exposing `strategy.request.data`."""
    return SimpleNamespace(request=SimpleNamespace(data=data))


def test_links_new_user_to_referrer() -> None:
    referrer = UserFactory()
    referee = UserFactory()
    strategy = _strategy({"referral_code": get_referral_code(referrer)})

    link_user_to_referrer(is_new=True, strategy=strategy, user=referee)

    referral = UserReferral.objects.get(referee=referee)
    assert referral.referrer == referrer


def test_noop_when_user_is_not_new() -> None:
    referrer = UserFactory()
    referee = UserFactory()
    strategy = _strategy({"referral_code": get_referral_code(referrer)})

    link_user_to_referrer(is_new=False, strategy=strategy, user=referee)

    assert not UserReferral.objects.filter(referee=referee).exists()


def test_noop_when_no_referral_code() -> None:
    referee = UserFactory()
    strategy = _strategy({})

    link_user_to_referrer(is_new=True, strategy=strategy, user=referee)

    assert not UserReferral.objects.filter(referee=referee).exists()
