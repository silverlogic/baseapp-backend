"""The read-only card hold admin and the summary helper for a target's admin."""

import datetime
from typing import Any

import pytest
import swapper
from django.contrib import admin

from baseapp_payments.admin import CardHoldAdmin, card_hold_admin_summary
from testproject.testapp.models import HoldableOrder

from ..factories import CardHoldFactory, HoldableOrderFactory, UserFactory

CardHold = swapper.load_model("baseapp_payments", "CardHold")

pytestmark = pytest.mark.django_db


@pytest.fixture
def superuser(db) -> Any:
    return UserFactory(is_staff=True, is_superuser=True)


def test_the_hold_admin_is_registered_and_read_only(superuser, rf, order) -> None:
    hold = CardHoldFactory(target=order)
    model_admin = admin.site._registry[CardHold]
    request = rf.get("/")
    request.user = superuser

    assert isinstance(model_admin, CardHoldAdmin)
    assert not model_admin.has_add_permission(request)
    assert not model_admin.has_change_permission(request, hold)
    assert not model_admin.has_delete_permission(request, hold)
    assert "stripe_payment_intent_id" in model_admin.get_readonly_fields(request, hold)


def test_the_changelist_renders(client, superuser, order) -> None:
    CardHoldFactory(target=order)
    client.force_login(superuser)

    response = client.get(f"/admin/{CardHold._meta.app_label}/{CardHold._meta.model_name}/")

    assert response.status_code == 200


def test_the_summary_of_a_held_target(order) -> None:
    CardHoldFactory(
        target=order,
        expires_at=datetime.datetime(2030, 3, 17, 12, 0, tzinfo=datetime.timezone.utc),
        failure_code="card_declined",
    )

    summary = card_hold_admin_summary(order)

    assert summary == (
        "Visa 4242 · 110.00 USD held · Authorized · expires 2030-03-17 12:00 UTC"
        " · failure: card_declined"
    )


def test_the_summary_without_a_hold(order) -> None:
    assert card_hold_admin_summary(order) == "No card hold"
    assert card_hold_admin_summary(HoldableOrder()) == "No card hold"


def test_the_summary_without_card_details(holder) -> None:
    order = HoldableOrderFactory(user=holder)
    CardHoldFactory(target=order, card_brand="", card_last4="", expires_at=None)

    assert card_hold_admin_summary(order) == "Card · 110.00 USD held · Authorized"


@pytest.mark.parametrize(
    "currency, cents, shown",
    [("eur", 123_456, "1,234.56 EUR"), ("jpy", 5_000, "5,000 JPY"), ("", 1_000, "10.00 USD")],
)
def test_the_summary_shows_the_holds_own_currency(holder, currency, cents, shown) -> None:
    order = HoldableOrderFactory(user=holder)
    CardHoldFactory(target=order, currency=currency, amount_cents=cents, expires_at=None)

    assert card_hold_admin_summary(order) == f"Visa 4242 · {shown} held · Authorized"


def test_a_prefetched_summary_costs_no_query(holder, django_assert_num_queries) -> None:
    """s3: for a ``list_display`` column, prefetch the holds once."""
    from baseapp_payments.models import CARD_HOLD_PREFETCH_PATH

    for _ in range(3):
        CardHoldFactory(target=HoldableOrderFactory(user=holder))
    HoldableOrderFactory(user=holder)  # no hold
    orders = list(HoldableOrder.objects.prefetch_related(CARD_HOLD_PREFETCH_PATH))

    with django_assert_num_queries(0):
        summaries = [card_hold_admin_summary(order) for order in orders]

    assert summaries.count("No card hold") == 1
    assert sum("110.00 USD held" in summary for summary in summaries) == 3


def test_the_summary_of_a_saved_card_shows_the_estimate(holder) -> None:
    order = HoldableOrderFactory(user=holder)
    CardHoldFactory(
        target=order,
        status=CardHold.Status.SAVED,
        amount_cents=0,
        buffer_percent=0,
        expires_at=None,
        stripe_payment_intent_id=None,
    )

    assert card_hold_admin_summary(order) == (
        "Visa 4242 · 100.00 USD estimated · Card saved, charged on the date"
    )
