"""Double submits and racing passes against a real, committing database: one target per
attempt, and no Stripe call while a row lock is held."""

import datetime
import threading
import uuid
from typing import Any
from unittest.mock import patch

import pytest
import swapper
from django.db import connection
from django.utils import timezone

from baseapp_payments import holds
from baseapp_payments.holds import (
    CaptureStatus,
    HoldRefused,
    PlacementResult,
    PlacementStatus,
    authorize_on_session,
    capture,
    complete_on_session,
)
from baseapp_payments.tasks import sweep_card_holds
from testproject.testapp.models import HoldableOrder

from ..factories import CardHoldFactory, HoldableOrderFactory, UserFactory
from ..fakes import STRIPE_CUSTOMER_ID

CardHold = swapper.load_model("baseapp_payments", "CardHold")


def in_two_days() -> datetime.date:
    """A date inside the window: held at checkout, on-session."""
    return timezone.localdate() + datetime.timedelta(days=2)


pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture(autouse=True)
def require_autocommit(settings) -> None:
    """A real, committing database: the outside-a-transaction guard is on, as in a project."""
    settings.BASEAPP_PAYMENTS_CARD_HOLD_REQUIRE_AUTOCOMMIT = True


def first_pass(user, attempt_id, link=None) -> PlacementResult:
    order = HoldableOrder(user=user, amount_cents=10_000, target_date=in_two_days())

    def save(hold) -> HoldableOrder:
        order.save()
        return order

    return authorize_on_session(
        user=user,
        attempt_id=attempt_id,
        payment_method_id="pm_visa",
        stripe_customer_id=STRIPE_CUSTOMER_ID,
        target=order,
        link=link or save,
        expected_amount_cents=10_000,
    )


def in_thread(function, results: list) -> threading.Thread:
    def run() -> None:
        try:
            results.append(function())
        finally:
            connection.close()

    return threading.Thread(target=run)


def test_a_double_submit_places_one_target(fake_stripe) -> None:
    user = UserFactory()
    attempt_id = uuid.uuid4()
    creating = threading.Event()
    proceed = threading.Event()

    def stall(params) -> None:
        creating.set()
        assert proceed.wait(10)

    fake_stripe.before_create = stall
    first: list = []
    thread = in_thread(lambda: first_pass(user, attempt_id), first)
    thread.start()
    assert creating.wait(10)

    # The second submit reaches Stripe while the first is still authorizing: Stripe's 409.
    fake_stripe.before_create = None
    second = first_pass(user, attempt_id)
    proceed.set()
    thread.join(10)

    assert second.status == PlacementStatus.IN_PROGRESS
    assert first[0].status == PlacementStatus.PLACED
    # Retrying the attempt now returns the placed target, without calling Stripe.
    calls = len(fake_stripe.calls)
    retried = first_pass(user, attempt_id)
    assert retried.status == PlacementStatus.PLACED
    assert retried.target == first[0].target
    assert len(fake_stripe.calls) == calls
    assert HoldableOrder.objects.count() == 1
    assert CardHold.objects.get().status == CardHold.Status.AUTHORIZED


def test_racing_second_passes_place_one_target_and_never_cancel(fake_stripe) -> None:
    user = UserFactory()
    attempt_id = uuid.uuid4()
    fake_stripe.next_outcome = ["requires_action"]
    assert first_pass(user, attempt_id).status == PlacementStatus.REQUIRES_ACTION
    (payment_intent_id,) = fake_stripe.intents
    fake_stripe.set_status(payment_intent_id, "requires_capture")
    both_retrieved = threading.Barrier(2, timeout=10)
    # Both requests pass the ownership checks before either locks the hold.
    fake_stripe.before_retrieve = lambda _id: both_retrieved.wait()

    def second_pass() -> PlacementResult:
        order = HoldableOrder(user=user, amount_cents=10_000, target_date=in_two_days())

        def save(hold) -> HoldableOrder:
            order.save()
            return order

        return complete_on_session(
            payment_intent_id,
            save,
            user=user,
            attempt_id=attempt_id,
            stripe_customer_id=STRIPE_CUSTOMER_ID,
            expected_amount_cents=10_000,
        )

    results: list = []
    threads = [in_thread(second_pass, results) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(10)

    assert [result.status for result in results] == [PlacementStatus.PLACED] * 2
    assert results[0].target.pk == results[1].target.pk
    assert HoldableOrder.objects.count() == 1
    assert CardHold.objects.get().status == CardHold.Status.AUTHORIZED
    assert fake_stripe.calls_to("PaymentIntent.cancel") == []


def test_the_pending_row_is_committed_before_linking(fake_stripe) -> None:
    user = UserFactory()
    seen = []
    original = holds.record_pending_hold

    def spy(**kwargs) -> Any:
        seen.append(connection.in_atomic_block)
        return original(**kwargs)

    with patch.object(holds, "record_pending_hold", side_effect=spy):
        assert first_pass(user, uuid.uuid4()).status == PlacementStatus.PLACED

    assert seen == [False]


def test_no_stripe_call_runs_while_a_row_lock_is_held(fake_stripe) -> None:
    user = UserFactory()
    in_transaction = []
    record = fake_stripe.record

    def record_and_check(name, *args, **kwargs) -> None:
        in_transaction.append((name, connection.in_atomic_block))
        record(name, *args, **kwargs)

    fake_stripe.record = record_and_check

    placed = first_pass(user, uuid.uuid4())

    def refuse(hold) -> HoldableOrder:
        raise HoldRefused()

    refused = first_pass(user, uuid.uuid4(), link=refuse)

    order = placed.target
    HoldableOrder.objects.filter(pk=order.pk).update(status=HoldableOrder.Status.CANCELLED)
    sweep_card_holds()
    HoldableOrderFactory(user=user)
    order.delete()

    assert placed.status == PlacementStatus.PLACED
    assert refused.status == PlacementStatus.REFUSED
    assert {name for name, _ in in_transaction} >= {
        "PaymentMethod.retrieve",
        "PaymentIntent.create",
        "PaymentIntent.cancel",
    }
    assert [name for name, locked in in_transaction if locked] == []
    assert CardHold.objects.filter(status=CardHold.Status.RELEASED).count() == 2


def test_a_concurrent_re_arm_places_once_and_cancels_the_loser(fake_stripe) -> None:
    order = HoldableOrderFactory(user=UserFactory())
    previous = CardHoldFactory(
        target=order, status=CardHold.Status.RELEASED, stripe_payment_intent_id="pi_old"
    )
    # Both requests pass the early check and authorize before either takes the locks.
    both_creating = threading.Barrier(2, timeout=10)
    fake_stripe.before_create = lambda params: both_creating.wait()

    def re_arm() -> PlacementResult:
        return authorize_on_session(
            user=order.user,
            attempt_id=uuid.uuid4(),
            payment_method_id="pm_visa",
            stripe_customer_id=STRIPE_CUSTOMER_ID,
            target=order,
            expected_amount_cents=10_000,
        )

    results: list = []
    threads = [in_thread(re_arm, results) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(10)

    assert sorted(result.status for result in results) == sorted(
        [PlacementStatus.PLACED, PlacementStatus.REFUSED]
    )
    hold = CardHold.objects.get(target_document__isnull=False)
    assert hold.pk == previous.pk
    assert hold.status == CardHold.Status.AUTHORIZED
    assert hold.previous_payment_intent_ids == ["pi_old"]
    (loser,) = [pi for pi in fake_stripe.intents if pi != hold.stripe_payment_intent_id]
    assert fake_stripe.status_of(loser) == "canceled"
    assert fake_stripe.status_of(hold.stripe_payment_intent_id) == "requires_capture"
    # The loser's row is released and unlinked; nothing is left pending.
    assert CardHold.objects.get(stripe_payment_intent_id=loser).status == (CardHold.Status.RELEASED)
    assert not CardHold.objects.filter(status=CardHold.Status.PENDING).exists()


def live_authorized_hold(fake_stripe) -> Any:
    hold = CardHoldFactory(target=HoldableOrderFactory(user=UserFactory()))
    fake_stripe.intents[hold.stripe_payment_intent_id] = {
        "id": hold.stripe_payment_intent_id,
        "object": "payment_intent",
        "status": "requires_capture",
        "amount": hold.amount_cents,
        "payment_method": "pm_visa",
        "capture_before": None,
        "amount_received": 0,
    }
    return hold


def test_a_capture_racing_a_charge_path_capture_takes_the_money_once(fake_stripe) -> None:
    """M3: the charge path holds the capture claim while it releases and charges; a
    concurrent capture that the hold would cover answers in_progress, calls no Stripe,
    and never charges. Retried after, it answers charged from the database."""
    hold = live_authorized_hold(fake_stripe)
    charging = threading.Event()
    proceed = threading.Event()
    charges = []

    def slow_charge(**kwargs) -> str:
        charges.append(kwargs["idempotency_key"])
        charging.set()
        assert proceed.wait(10)
        return "ch_new"

    results: list = []
    thread = in_thread(lambda: capture(hold.pk, 20_000, charge=slow_charge), results)
    thread.start()
    assert charging.wait(10)

    calls = len(fake_stripe.calls)
    racing = capture(hold.pk, 10_000, charge=slow_charge)
    proceed.set()
    thread.join(10)

    assert racing.status == CaptureStatus.IN_PROGRESS
    assert len(fake_stripe.calls) == calls
    assert results[0].status == CaptureStatus.CHARGED
    assert fake_stripe.calls_to("PaymentIntent.capture") == []
    retried = capture(hold.pk, 10_000, charge=slow_charge)
    assert retried.status == CaptureStatus.CHARGED and retried.charge is None
    assert len(charges) == 1
    hold.refresh_from_db()
    assert hold.capture_claimed_at is None and hold.charged_at is not None


def test_racing_captures_on_the_charge_path_charge_once(fake_stripe) -> None:
    hold = live_authorized_hold(fake_stripe)
    both = threading.Barrier(2, timeout=10)
    charges = []

    def charge(**kwargs) -> str:
        charges.append(kwargs["idempotency_key"])
        return "ch_new"

    def racer() -> Any:
        both.wait()
        return capture(hold.pk, 20_000, charge=charge)

    results: list = []
    threads = [in_thread(racer, results) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(10)

    assert len(charges) == 1
    assert sorted(result.status for result in results) in (
        sorted([CaptureStatus.CHARGED, CaptureStatus.IN_PROGRESS]),
        [CaptureStatus.CHARGED, CaptureStatus.CHARGED],
    )
    assert len(fake_stripe.calls_to("PaymentIntent.cancel")) == 1


def test_capture_runs_no_stripe_call_inside_a_transaction(fake_stripe) -> None:
    hold = live_authorized_hold(fake_stripe)
    in_transaction = []
    record = fake_stripe.record

    def record_and_check(name, *args, **kwargs) -> None:
        in_transaction.append(connection.in_atomic_block)
        record(name, *args, **kwargs)

    fake_stripe.record = record_and_check

    assert capture(hold.pk, 10_000, charge=lambda **_: None).status == CaptureStatus.CAPTURED
    assert in_transaction == [False]
