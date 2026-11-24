"""Staff retries against a real, committing database: two retries at once place one
attempt, and a retry racing a cancel, keep, the sweep or a webhook never leaves two live
authorizations. Stripe is never called while a row lock is held."""

import datetime
import threading
from typing import Any

import pytest
import swapper
from django.db import connection, transaction
from django.utils import timezone

from baseapp_payments.holds import (
    CardHoldInTransaction,
    PlacementStatus,
    RetryRefusal,
    cancel_failed_hold,
    keep_failed_hold,
    reconcile_payment_intent,
    release,
    retry_failed_hold,
)
from baseapp_payments.tasks import sweep_card_holds
from testproject.testapp.models import HoldableOrder

from ..card_hold_factories import CardHoldFactory, HoldableOrderFactory
from ..factories import UserFactory

CardHold = swapper.load_model("baseapp_payments", "CardHold")

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture(autouse=True)
def require_autocommit(settings) -> None:
    settings.BASEAPP_PAYMENTS_CARD_HOLD_REQUIRE_AUTOCOMMIT = True


def failed_hold() -> Any:
    today = timezone.localdate()
    order = HoldableOrderFactory(user=UserFactory(), target_date=today + datetime.timedelta(3))
    return CardHoldFactory(
        target=order,
        status=CardHold.Status.FAILED,
        failed_at=timezone.now(),
        failure_code="card_declined",
        stripe_payment_intent_id="pi_failed",
        expires_at=None,
        hold_on=today,
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
    """Stall the next create inside Stripe, so a racing call runs meanwhile."""
    creating, proceed = threading.Event(), threading.Event()

    def stall(params) -> None:
        creating.set()
        assert proceed.wait(10)

    fake_stripe.before_create = stall
    return creating, proceed


def start_stalled_retry(fake_stripe, hold) -> tuple[threading.Thread, list, threading.Event]:
    creating, proceed = stall_creates(fake_stripe)
    results: list = []
    thread = in_thread(lambda: retry_failed_hold(hold.pk, None), results)
    assert creating.wait(10)
    fake_stripe.before_create = None
    return thread, results, proceed


def assert_no_lock_held(hold) -> None:
    with transaction.atomic():
        HoldableOrder.objects.select_for_update(nowait=True).get(pk=hold.target.pk)
        CardHold.objects.select_for_update(nowait=True).get(pk=hold.pk)


def test_two_retries_at_once_place_one_attempt(fake_stripe) -> None:
    hold = failed_hold()
    thread, first, proceed = start_stalled_retry(fake_stripe, hold)

    # The claim committed before Stripe was called: the second click sees it, calls
    # nothing, and takes the row locks without waiting.
    second = retry_failed_hold(hold.pk, None)
    assert_no_lock_held(hold)
    proceed.set()
    thread.join(10)

    assert second.status == PlacementStatus.IN_PROGRESS and second.refusal is None
    assert first[0].status == PlacementStatus.PLACED
    assert len(fake_stripe.calls_to("PaymentIntent.create")) == 1
    hold.refresh_from_db()
    assert hold.status == CardHold.Status.AUTHORIZED and hold.retry_count == 1
    assert len(fake_stripe.live_authorizations()) == 1


def test_a_retry_racing_a_cancel_strands_no_authorization(fake_stripe) -> None:
    hold = failed_hold()
    thread, retrying, proceed = start_stalled_retry(fake_stripe, hold)

    # Staff can't cancel a hold whose retry is in flight as a failed one...
    assert cancel_failed_hold(hold.pk, None) is False
    assert keep_failed_hold(hold.pk, None) is False
    # ...and cancelling the target leaves it to the placement, which settles it.
    HoldableOrder.objects.filter(pk=hold.target.pk).update(status="cancelled")
    assert release(hold.pk) is False
    proceed.set()
    thread.join(10)

    assert retrying[0].status == PlacementStatus.REFUSED
    hold.refresh_from_db()
    assert hold.status == CardHold.Status.RELEASED and hold.release_reason == "cancelled"
    assert fake_stripe.live_authorizations() == []


def test_a_cancel_first_means_no_retry(fake_stripe) -> None:
    hold = failed_hold()

    assert cancel_failed_hold(hold.pk, None) is True
    result = retry_failed_hold(hold.pk, None)

    assert result.refusal == RetryRefusal.NOT_FAILED
    assert fake_stripe.calls == []


def test_a_retry_racing_the_sweep_places_once(fake_stripe) -> None:
    hold = failed_hold()
    thread, retrying, proceed = start_stalled_retry(fake_stripe, hold)

    sweep_card_holds()  # sees a scheduled hold under a live claim: queues nothing
    proceed.set()
    thread.join(10)

    assert retrying[0].status == PlacementStatus.PLACED
    assert len(fake_stripe.calls_to("PaymentIntent.create")) == 1


def test_a_webhook_racing_a_retry_settles_it_once(fake_stripe) -> None:
    hold = failed_hold()
    thread, retrying, proceed = start_stalled_retry(fake_stripe, hold)
    proceed.set()
    thread.join(10)
    (payment_intent_id,) = fake_stripe.intents

    # A webhook for the retry's authorization, after the retry recorded it.
    assert reconcile_payment_intent(hold.pk, payment_intent_id) == "current"

    assert retrying[0].status == PlacementStatus.PLACED
    assert fake_stripe.live_authorizations() == [payment_intent_id]


def test_retrying_refuses_inside_a_transaction(fake_stripe) -> None:
    hold = failed_hold()

    with pytest.raises(CardHoldInTransaction), transaction.atomic():
        retry_failed_hold(hold.pk, None)

    hold.refresh_from_db()
    assert hold.status == CardHold.Status.FAILED and hold.retry_count == 0
    assert fake_stripe.calls == []
