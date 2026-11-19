from collections.abc import Generator
from typing import Any
from unittest.mock import patch

import pytest
from django.test import override_settings

from baseapp_core.tests.fixtures import *  # noqa: F403, F401

from .fakes import STRIPE_CUSTOMER_ID, TEST_KEY, FakeStripe


@pytest.fixture
def fake_stripe() -> Generator[FakeStripe, None, None]:
    """A configured Stripe key and an in-memory Stripe behind the card holds' ``get_stripe``,
    with the customer's saved Visa ``pm_visa``."""
    fake = FakeStripe()
    fake.add_card("pm_visa")
    with (
        override_settings(STRIPE_SECRET_KEY=TEST_KEY),
        patch("baseapp_payments.utils.get_stripe", return_value=fake),
    ):
        yield fake


@pytest.fixture
def no_stripe_key() -> Generator[None, None, None]:
    with override_settings(STRIPE_SECRET_KEY=""):
        yield


@pytest.fixture
def stripe_customer_id() -> str:
    return STRIPE_CUSTOMER_ID


@pytest.fixture
def holder(db) -> Any:
    """The customer placing holds."""
    from .factories import UserFactory

    return UserFactory()


@pytest.fixture
def order(holder) -> Any:
    """A saved, open $100.00 target of ``holder``."""
    from .factories import HoldableOrderFactory

    return HoldableOrderFactory(user=holder)
