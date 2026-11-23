"""Factories for card hold tests.

Kept apart from ``factories.py`` because they resolve models at import time that only exist
where card holds are set up: ``testapp.HoldableOrder`` (the test project's target) and the
swappable ``CardHold`` model. A project that re-runs this package's other tests
(``from baseapp_payments.tests.test_... import *``) imports ``factories.py`` without either.
"""

import datetime

import factory
import swapper
from django.utils import timezone

from baseapp_core.models import DocumentId

from .factories import UserFactory


class HoldableOrderFactory(factory.django.DjangoModelFactory):
    """The test project's card hold target (testproject.testapp.HoldableOrder)."""

    class Meta:
        model = "testapp.HoldableOrder"

    user = factory.SubFactory(UserFactory)
    amount_cents = 10_000
    # Charged in two days: a hold is only for a target charged in the future, and two
    # days is inside the default window, so it is held at checkout.
    target_date = factory.LazyFunction(lambda: timezone.localdate() + datetime.timedelta(days=2))


class CardHoldFactory(factory.django.DjangoModelFactory):
    """A hold as placing leaves it: authorized for $100.00 + 10%, linked when given a
    ``target``."""

    class Meta:
        model = swapper.load_model("baseapp_payments", "CardHold")
        exclude = ("target",)

    target = None
    customer = factory.LazyAttribute(
        lambda o: o.target.user if o.target is not None else UserFactory()
    )
    stripe_customer_id = "cus_holder"
    attempt_id = factory.Faker("uuid4", cast_to=None)
    stripe_payment_intent_id = factory.Sequence(lambda n: f"pi_factory_{n}")
    stripe_payment_method_id = "pm_visa"
    card_brand = "visa"
    card_last4 = "4242"
    card_exp_month = 8
    card_exp_year = 2099
    card_funding = "credit"
    estimated_amount_cents = 10_000
    buffer_percent = 10
    amount_cents = 11_000
    status = "authorized"
    target_document = factory.LazyAttribute(
        lambda o: DocumentId.get_or_create_for_object(o.target) if o.target is not None else None
    )
    expires_at = factory.LazyFunction(lambda: timezone.now() + datetime.timedelta(days=6))
