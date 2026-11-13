"""Deferred placement against a real, committing database: racing sweeps place once,
and a sweep racing reschedule() or a cancel never places twice or strands an
authorization. Stripe is never called while a row lock is held."""

import datetime
import threading
from collections.abc import Generator
from typing import Any

import pytest
import swapper
from constance.test import override_config
from django.db import connection, transaction
from django.utils import timezone

from baseapp_payments.holds import (
    CardHoldInTransaction,
    PlacementStatus,
    place_scheduled,
    release,
    reschedule,
    reschedule_hold,
)
from testproject.testapp.models import HoldableOrder

from ..factories import CardHoldFactory, HoldableOrderFactory, UserFactory

CardHold = swapper.load_model("baseapp_payments", "CardHold")

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture(autouse=True)
def require_autocommit(settings) -> None:
    settings.BASEAPP_PAYMENTS_CARD_HOLD_REQUIRE_AUTOCOMMIT = True


@pytest.fixture(autouse=True)
def deferral() -> Generator[None, None, None]:
    with override_config(CARD_HOLDS_DEFERRAL_ENABLED=True):
        yield


def due_hold(**fields: Any) -> Any:
    today = timezone.localdate()
    order = HoldableOrderFactory(user=UserFactory(), target_date=today + datetime.timedelta(5))
    return CardHoldFactory(
        target=order,
        status=CardHold.Status.SCHEDULED,
        stripe_payment_intent_id=None,
        expires_at=None,
        hold_on=today,
        **fields,
    )


def in_thread(function, results: list) -> threading.Thread:
    def run() -> None:
        try:
            results.append(function())
        finally:
            connection.close()

    thread = threading.Thread(target=run)
    thread.start()
    return thread


def stall_creates(fake_stripe) -> tuple[threading.Event, threading.Event]:
    """Stall the next off-session create inside Stripe, and assert no row lock is held
    there: another connection can lock the hold and its target without waiting."""
    creating, proceed = threading.Event(), threading.Event()

    def stall(params) -> None:
        creating.set()
        assert proceed.wait(10)

    fake_stripe.before_create = stall
    return creating, proceed


def test_racing_sweeps_place_once(fake_stripe) -> None:
    hold = due_hold()
    creating, proceed = stall_creates(fake_stripe)
    first: list = []
    thread = in_thread(lambda: place_scheduled(hold.pk), first)
    assert creating.wait(10)

    # The claim committed before Stripe was called: a second sweep (or a redelivered
    # task) sees it and calls nothing, and takes the row locks without waiting.
    fake_stripe.before_create = None
    second = place_scheduled(hold.pk)
    with transaction.atomic():
        HoldableOrder.objects.select_for_update(nowait=True).get(pk=hold.target.pk)
        CardHold.objects.select_for_update(nowait=True).get(pk=hold.pk)
    proceed.set()
    thread.join(10)

    assert second.status == PlacementStatus.IN_PROGRESS
    assert first[0].status == PlacementStatus.PLACED
    assert len(fake_stripe.calls_to("PaymentIntent.create")) == 1
    assert CardHold.objects.get(pk=hold.pk).status == CardHold.Status.AUTHORIZED


def test_a_sweep_racing_reschedule_places_once_and_reschedule_waits(fake_stripe) -> None:
    hold = due_hold()
    creating, proceed = stall_creates(fake_stripe)
    placing: list = []
    thread = in_thread(lambda: place_scheduled(hold.pk), placing)
    assert creating.wait(10)

    order = HoldableOrder.objects.get(pk=hold.target.pk)
    order.target_date = timezone.localdate() + datetime.timedelta(days=30)
    order.save()
    racing = reschedule(order)
    proceed.set()
    thread.join(10)

    # The placement is under way: reschedule answers in_progress (its task retries)...
    assert racing.status == PlacementStatus.IN_PROGRESS
    assert placing[0].status == PlacementStatus.PLACED
    # ...and once it settled, moves the placed hold back to scheduled.
    after = reschedule_hold(hold.pk)
    assert after.status == PlacementStatus.SCHEDULED
    hold.refresh_from_db()
    assert hold.status == CardHold.Status.SCHEDULED
    (payment_intent_id,) = fake_stripe.intents
    assert hold.previous_payment_intent_ids == [payment_intent_id]
    assert fake_stripe.status_of(payment_intent_id) == "canceled"


def test_a_sweep_racing_a_cancel_strands_no_authorization(fake_stripe) -> None:
    hold = due_hold()
    creating, proceed = stall_creates(fake_stripe)
    placing: list = []
    thread = in_thread(lambda: place_scheduled(hold.pk), placing)
    assert creating.wait(10)

    HoldableOrder.objects.filter(pk=hold.target.pk).update(status="cancelled")
    # The release can't tell whether Stripe will authorize: it leaves the hold to the
    # placement, which settles it.
    assert release(hold.pk) is False
    proceed.set()
    thread.join(10)

    assert placing[0].status == PlacementStatus.REFUSED
    hold.refresh_from_db()
    assert hold.status == CardHold.Status.RELEASED
    assert hold.release_reason == "cancelled"
    (payment_intent_id,) = fake_stripe.intents
    assert hold.stripe_payment_intent_id == payment_intent_id
    assert fake_stripe.status_of(payment_intent_id) == "canceled"


def test_a_cancel_first_means_no_placement(fake_stripe) -> None:
    hold = due_hold()
    HoldableOrder.objects.filter(pk=hold.target.pk).update(status="cancelled")

    assert release(hold.pk) is True
    assert place_scheduled(hold.pk) is None

    assert fake_stripe.calls == []


def test_placing_and_rescheduling_refuse_inside_a_transaction(fake_stripe) -> None:
    hold = due_hold()

    with pytest.raises(CardHoldInTransaction), transaction.atomic():
        place_scheduled(hold.pk)
    with pytest.raises(CardHoldInTransaction), transaction.atomic():
        reschedule_hold(hold.pk)

    assert fake_stripe.calls == []
