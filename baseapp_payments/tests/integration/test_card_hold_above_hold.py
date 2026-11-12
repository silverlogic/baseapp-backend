"""A final amount above the hold (BA-3483): the hold is captured in full, then the
difference is charged to the same card; payment status, signals, fees and the invoice."""

import datetime
from collections.abc import Generator
from typing import Any
from unittest.mock import Mock, patch

import pytest
import stripe
import swapper
from django.utils import timezone

from baseapp_payments.holds import (
    CHARGE_KEY_TTL,
    CaptureStatus,
    attach_payments_to_invoice,
    capture,
    difference_idempotency_key,
    hold_payment_intent_ids,
    mark_paid_outside,
    reconcile_payment_intent,
    record_fees,
)
from baseapp_payments.signals import difference_charge_failed, payment_status_changed
from testproject.testapp.models import HoldableOrder

from ..factories import CardHoldFactory, HoldableOrderFactory
from ..fakes import (
    STRIPE_CUSTOMER_ID,
    FakeStripe,
    api_error,
    card_declined,
    connection_error,
    idempotency_error,
    project_charge,
)

CardHold = swapper.load_model("baseapp_payments", "CardHold")

pytestmark = pytest.mark.django_db

HELD = 11_000  # CardHoldFactory: $100.00 + 10%


def live_hold(fake_stripe: FakeStripe, **fields: Any) -> Any:
    """An authorized hold whose PaymentIntent the fake holds, as placing leaves it."""
    hold = CardHoldFactory(**fields)
    fake_stripe.intents[hold.stripe_payment_intent_id] = {
        "id": hold.stripe_payment_intent_id,
        "object": "payment_intent",
        "status": "requires_capture",
        "capture_method": "manual",
        "amount": hold.amount_cents,
        "currency": "usd",
        "customer": STRIPE_CUSTOMER_ID,
        "metadata": {"card_hold_id": str(hold.pk)},
        "payment_method": "pm_visa",
        "capture_before": None,
        "amount_received": 0,
        "created": 0,
    }
    return hold


def differences(fake_stripe: FakeStripe) -> list[dict[str, Any]]:
    """The difference PaymentIntents sent to Stripe, with their parameters."""
    return [
        params
        for _args, params in fake_stripe.calls_to("PaymentIntent.create")
        if params.get("metadata", {}).get("kind") == "difference"
    ]


@pytest.fixture
def signals() -> Generator[dict[str, list], None, None]:
    """Every payment status change and difference failure sent, in order. Sent at once
    here instead of on commit (the test's transaction never commits);
    ``test_signals_wait_for_the_commit`` pins the on-commit part."""
    heard: dict[str, list] = {"status": [], "failed": []}

    def on_status(sender: Any, **kwargs: Any) -> None:
        heard["status"].append((kwargs["previous"], kwargs["payment_status"]))
        assert kwargs["target"] is not None

    def on_failed(sender: Any, **kwargs: Any) -> None:
        heard["failed"].append((kwargs["amount_due_cents"], kwargs["error_code"]))
        assert kwargs["hold"].pk and kwargs["target"] is not None

    def send_now(signal: Any, **kwargs: Any) -> None:
        signal.send_robust(sender=CardHold, **kwargs)

    payment_status_changed.connect(on_status, weak=False)
    difference_charge_failed.connect(on_failed, weak=False)
    try:
        with patch("baseapp_payments.holds.send_on_commit", side_effect=send_now):
            yield heard
    finally:
        payment_status_changed.disconnect(on_status)
        difference_charge_failed.disconnect(on_failed)


def reloaded(hold: Any) -> Any:
    hold.refresh_from_db()
    return hold


class TestFinalAmounts:
    """The story's test data: a cent below, equal to, and above the hold."""

    @pytest.mark.parametrize("amount", [HELD - 1, HELD], ids=["a_cent_below", "equal"])
    def test_within_the_hold_is_one_capture(self, order, fake_stripe, signals, amount) -> None:
        hold = live_hold(fake_stripe, target=order)
        charge = Mock()

        result = capture(hold.pk, amount, charge=charge)

        assert result.status == CaptureStatus.CAPTURED
        # A partial capture: Stripe releases the rest of the hold itself.
        assert fake_stripe.captures == [(hold.stripe_payment_intent_id, amount)]
        assert differences(fake_stripe) == []
        charge.assert_not_called()
        hold = reloaded(hold)
        assert hold.payment_status == CardHold.PaymentStatus.PAID
        assert hold.capture_fee_cents == FakeStripe.fee_for(amount)
        assert hold.fee_currency == "usd"
        assert hold_payment_intent_ids(hold) == [hold.stripe_payment_intent_id]
        assert signals == {"status": [("unpaid", "paid")], "failed": []}

    def test_above_the_hold_captures_it_all_then_charges_the_difference(
        self, order, fake_stripe, signals
    ) -> None:
        hold = live_hold(fake_stripe, target=order)
        events = []

        def observe(params: dict) -> None:
            events.append(fake_stripe.status_of(hold.stripe_payment_intent_id))

        fake_stripe.before_create = observe
        charge = Mock()

        result = capture(hold.pk, 12_000, charge=charge)

        assert result.status == CaptureStatus.PAID
        # The hold first, in full: a refused difference never costs the held amount.
        assert events == ["succeeded"]
        assert fake_stripe.captures == [(hold.stripe_payment_intent_id, HELD)]
        ((difference),) = differences(fake_stripe)
        assert difference == {
            "amount": 1_000,
            "currency": "usd",
            "customer": STRIPE_CUSTOMER_ID,
            "payment_method": "pm_visa",
            "payment_method_types": ["card"],
            "confirm": True,
            "off_session": True,
            "metadata": {
                "card_hold_id": str(hold.pk),
                "kind": "difference",
                "difference_key": difference_idempotency_key(hold.pk),
            },
            "expand": ["latest_charge.balance_transaction"],
            "idempotency_key": f"testproject-difference-{hold.pk}-0",
        }
        charge.assert_not_called()
        hold = reloaded(hold)
        assert hold.status == CardHold.Status.CAPTURED
        assert hold.captured_amount_cents == HELD
        assert hold.difference_amount_cents == 1_000
        assert hold.difference_payment_intent_id == result.payment_intent.id
        assert hold.difference_charged_at is not None
        assert hold.payment_status == CardHold.PaymentStatus.PAID
        # Stripe's actual fee, per payment.
        assert hold.capture_fee_cents == FakeStripe.fee_for(HELD)
        assert hold.difference_fee_cents == FakeStripe.fee_for(1_000)
        # Both payments belong to the same hold, so to the same target.
        assert hold_payment_intent_ids(hold) == [
            hold.stripe_payment_intent_id,
            hold.difference_payment_intent_id,
        ]
        assert fake_stripe.intents[hold.difference_payment_intent_id]["metadata"][
            "card_hold_id"
        ] == str(hold.pk)
        assert signals == {"status": [("unpaid", "paid")], "failed": []}

    def test_a_retry_answers_paid_from_the_database(self, order, fake_stripe, signals) -> None:
        hold = live_hold(fake_stripe, target=order)
        capture(hold.pk, 12_000, charge=Mock())
        calls = len(fake_stripe.calls)

        again = capture(hold.pk, 12_000, charge=Mock())
        other = capture(hold.pk, 13_000, charge=Mock())

        assert again.status == CaptureStatus.PAID
        assert other.status == CaptureStatus.NOT_CAPTURED
        assert len(fake_stripe.calls) == calls
        assert signals["status"] == [("unpaid", "paid")]

    def test_the_totals_count_both_payments(self, order, fake_stripe) -> None:
        hold = live_hold(fake_stripe, target=order)
        capture(hold.pk, 12_000, charge=Mock())

        totals = CardHold.objects.with_payment_totals().get(pk=hold.pk)

        assert totals.paid_cents == 12_000
        assert totals.fees_cents == FakeStripe.fee_for(HELD) + FakeStripe.fee_for(1_000)


def test_signals_wait_for_the_commit(
    order, fake_stripe, django_capture_on_commit_callbacks
) -> None:
    hold = live_hold(fake_stripe, target=order)
    fake_stripe.next_outcome.append("card_declined")
    heard = []

    def receiver(sender: Any, **kwargs: Any) -> None:
        heard.append(sender)

    difference_charge_failed.connect(receiver, weak=False)
    try:
        with django_capture_on_commit_callbacks(execute=True) as callbacks:
            capture(hold.pk, 12_000, charge=Mock())
            assert heard == []
    finally:
        difference_charge_failed.disconnect(receiver)

    assert heard == [CardHold]
    assert len(callbacks) >= 2  # payment_status_changed, difference_charge_failed


class TestExpiredOrNoHold:
    def test_an_expired_hold_closed_above_its_estimate_is_one_full_charge(
        self, order, fake_stripe, signals
    ) -> None:
        hold = live_hold(
            fake_stripe, target=order, expires_at=timezone.now() - datetime.timedelta(hours=1)
        )

        result = capture(hold.pk, 12_000, charge=project_charge(fake_stripe, amount=12_000))

        assert result.status == CaptureStatus.CHARGED
        assert fake_stripe.captures == []
        assert differences(fake_stripe) == []
        hold = reloaded(hold)
        assert hold.status == CardHold.Status.RELEASED
        assert hold.charge_payment_intent_id == result.charge.id
        assert hold.charge_amount_cents == 12_000
        assert hold.payment_status == CardHold.PaymentStatus.PAID
        assert hold_payment_intent_ids(hold) == [hold.charge_payment_intent_id]
        # The project's charge didn't expand the balance transaction: read later.
        assert hold.charge_fee_cents is None
        assert record_fees(hold.pk) == 1
        assert reloaded(hold).charge_fee_cents == FakeStripe.fee_for(12_000)
        assert signals == {"status": [("unpaid", "paid")], "failed": []}

    def test_a_lapsed_authorization_is_one_full_charge(self, order, fake_stripe) -> None:
        hold = live_hold(fake_stripe, target=order)
        fake_stripe.lapse(hold.stripe_payment_intent_id, canceled=False)

        result = capture(hold.pk, 12_000, charge=project_charge(fake_stripe, amount=12_000))

        assert result.status == CaptureStatus.CHARGED
        assert differences(fake_stripe) == []
        hold = reloaded(hold)
        assert hold.difference_amount_cents is None
        assert hold.payment_status == CardHold.PaymentStatus.PAID

    def test_a_saved_card_is_one_full_charge(self, order, fake_stripe) -> None:
        """uses_holds = False: nothing held, the card charged once on the date."""
        hold = CardHoldFactory(
            target=order, status=CardHold.Status.SAVED, stripe_payment_intent_id=None
        )

        result = capture(hold.pk, 12_000, charge=project_charge(fake_stripe, amount=12_000))

        assert result.status == CaptureStatus.CHARGED
        assert reloaded(hold).payment_status == CardHold.PaymentStatus.PAID

    def test_a_charge_that_returns_no_payment_intent_records_no_payment(
        self, order, fake_stripe
    ) -> None:
        hold = CardHoldFactory(
            target=order, status=CardHold.Status.SAVED, stripe_payment_intent_id=None
        )

        capture(hold.pk, 12_000, charge=Mock(return_value="ch_elsewhere"))

        hold = reloaded(hold)
        assert hold.charge_payment_intent_id is None
        assert hold.payment_status == CardHold.PaymentStatus.PAID
        assert hold_payment_intent_ids(hold) == []


class TestDifferenceDeclined:
    def test_the_held_amount_stays_paid_and_the_rest_is_due(
        self, order, fake_stripe, signals
    ) -> None:
        hold = live_hold(fake_stripe, target=order)
        fake_stripe.next_outcome.append("insufficient_funds")

        result = capture(hold.pk, 12_000, charge=Mock())

        assert result.status == CaptureStatus.PARTIALLY_PAID
        assert isinstance(result.error, stripe.CardError)
        assert fake_stripe.captures == [(hold.stripe_payment_intent_id, HELD)]
        hold = reloaded(hold)
        assert hold.status == CardHold.Status.CAPTURED
        assert hold.payment_status == CardHold.PaymentStatus.PARTIALLY_PAID
        assert hold.difference_key == ""
        assert hold.difference_generation == 1
        assert hold.difference_failure_code == "insufficient_funds"
        assert hold.difference_charged_at is None
        assert hold_payment_intent_ids(hold) == [hold.stripe_payment_intent_id]
        assert signals == {
            "status": [("unpaid", "partially_paid")],
            "failed": [(1_000, "insufficient_funds")],
        }

    def test_then_marked_paid_outside_it_is_paid_and_never_charged(
        self, order, fake_stripe, signals, holder
    ) -> None:
        hold = live_hold(fake_stripe, target=order)
        fake_stripe.next_outcome.append("card_declined")
        capture(hold.pk, 12_000, charge=Mock())

        assert mark_paid_outside(hold.pk, holder) is True
        assert mark_paid_outside(hold.pk, holder) is False
        again = capture(hold.pk, 12_000, charge=Mock())

        assert again.status == CaptureStatus.PAID
        assert len(differences(fake_stripe)) == 1
        hold = reloaded(hold)
        assert hold.payment_status == CardHold.PaymentStatus.PAID
        assert hold.paid_outside_at is not None and hold.paid_outside_by == holder
        assert signals["status"] == [("unpaid", "partially_paid"), ("partially_paid", "paid")]
        assert len(signals["failed"]) == 1

    def test_retried_it_is_charged_with_a_new_key(self, order, fake_stripe, signals) -> None:
        hold = live_hold(fake_stripe, target=order)
        fake_stripe.next_outcome.append("card_declined")
        capture(hold.pk, 12_000, charge=Mock())

        result = capture(hold.pk, 12_000, charge=Mock())

        assert result.status == CaptureStatus.PAID
        keys = [params["idempotency_key"] for params in differences(fake_stripe)]
        assert keys == [
            difference_idempotency_key(hold.pk, 0),
            difference_idempotency_key(hold.pk, 1),
        ]
        assert len(fake_stripe.captures) == 1
        hold = reloaded(hold)
        assert hold.payment_status == CardHold.PaymentStatus.PAID
        assert hold.difference_failure_code == ""
        assert signals["status"] == [("unpaid", "partially_paid"), ("partially_paid", "paid")]

    def test_a_refused_request_is_a_decline_too(self, order, fake_stripe, signals) -> None:
        hold = live_hold(fake_stripe, target=order)
        fake_stripe.fail_next(
            "PaymentIntent.create",
            stripe.InvalidRequestError("No such PaymentMethod", None, code="resource_missing"),
        )

        result = capture(hold.pk, 12_000, charge=Mock())

        assert result.status == CaptureStatus.PARTIALLY_PAID
        assert reloaded(hold).difference_failure_code == "resource_missing"
        assert signals["failed"] == [(1_000, "resource_missing")]

    def test_a_payment_intent_left_needing_a_card_is_a_decline(
        self, order, fake_stripe, signals
    ) -> None:
        hold = live_hold(fake_stripe, target=order)
        fake_stripe.next_outcome.append("requires_payment_method")

        result = capture(hold.pk, 12_000, charge=Mock())

        assert result.status == CaptureStatus.PARTIALLY_PAID
        assert reloaded(hold).payment_status == CardHold.PaymentStatus.PARTIALLY_PAID
        assert len(signals["failed"]) == 1

    def test_a_cancelled_target_isnt_charged_again(self, order, fake_stripe) -> None:
        hold = live_hold(fake_stripe, target=order)
        fake_stripe.next_outcome.append("card_declined")
        capture(hold.pk, 12_000, charge=Mock())
        HoldableOrder.objects.filter(pk=order.pk).update(status=HoldableOrder.Status.CANCELLED)

        result = capture(hold.pk, 12_000, charge=Mock())

        assert result.status == CaptureStatus.PARTIALLY_PAID
        assert len(differences(fake_stripe)) == 1

    def test_a_decline_of_the_hold_itself_is_never_partially_paid(
        self, order, fake_stripe, signals
    ) -> None:
        """partially_paid has one way in: the hold captured, the difference refused."""
        hold = live_hold(fake_stripe, target=order)
        fake_stripe.fail_next("PaymentIntent.capture", card_declined())

        result = capture(hold.pk, 12_000, charge=Mock())

        assert result.status == CaptureStatus.DECLINED
        assert differences(fake_stripe) == []
        assert reloaded(hold).payment_status == CardHold.PaymentStatus.UNPAID
        assert signals == {"status": [], "failed": []}


class TestRetries:
    def test_a_capture_retried_after_the_hold_was_captured_but_before_the_difference(
        self, order, fake_stripe, signals
    ) -> None:
        """The process died between recording the capture and claiming the difference."""
        hold = live_hold(fake_stripe, target=order)
        with patch("baseapp_payments.holds._claim_difference", side_effect=RuntimeError("died")):
            with pytest.raises(RuntimeError):
                capture(hold.pk, 12_000, charge=Mock())
        assert reloaded(hold).status == CardHold.Status.CAPTURED
        assert reloaded(hold).payment_status == CardHold.PaymentStatus.UNPAID

        result = capture(hold.pk, 12_000, charge=Mock())

        assert result.status == CaptureStatus.PAID
        assert len(fake_stripe.calls_to("PaymentIntent.capture")) == 1
        assert len(differences(fake_stripe)) == 1
        assert signals["status"] == [("unpaid", "paid")]

    def test_a_capture_whose_answer_was_lost_is_recorded_by_the_webhook_first(
        self, order, fake_stripe, signals
    ) -> None:
        """The hold's capture reached Stripe; its answer didn't. The webhook records it
        captured, but not paid: a difference is planned. The retry charges it."""
        hold = live_hold(fake_stripe, target=order)
        with patch("baseapp_payments.holds.mark_captured"):
            with patch("baseapp_payments.holds._settle_difference", side_effect=RuntimeError):
                with pytest.raises(RuntimeError):
                    capture(hold.pk, 12_000, charge=Mock())
        assert reconcile_payment_intent(hold.pk, hold.stripe_payment_intent_id) == "captured"
        assert reloaded(hold).payment_status == CardHold.PaymentStatus.UNPAID

        result = capture(hold.pk, 12_000, charge=Mock())

        assert result.status == CaptureStatus.PAID
        assert len(fake_stripe.captures) == 1
        assert signals["status"] == [("unpaid", "paid")]

    def test_the_difference_got_no_answer_and_is_resumed_with_its_key(
        self, order, fake_stripe
    ) -> None:
        hold = live_hold(fake_stripe, target=order)
        fake_stripe.fail_next("PaymentIntent.create", connection_error())

        with pytest.raises(stripe.APIConnectionError):
            capture(hold.pk, 12_000, charge=Mock())
        hold = reloaded(hold)
        assert hold.difference_key == difference_idempotency_key(hold.pk)
        assert hold.payment_status == CardHold.PaymentStatus.UNPAID

        result = capture(hold.pk, 12_000, charge=Mock())

        assert result.status == CaptureStatus.PAID
        keys = {params["idempotency_key"] for params in differences(fake_stripe)}
        assert keys == {difference_idempotency_key(hold.pk)}
        assert len(fake_stripe.captures) == 1

    def test_a_difference_charged_behind_a_5xx_is_never_charged_twice(
        self, order, fake_stripe, signals
    ) -> None:
        """Stripe charged it and answered 500, which it replays for the key: the retry
        gets the 500 again, and the webhook records the payment."""
        hold = live_hold(fake_stripe, target=order)
        fake_stripe.fail_behind_next()

        with pytest.raises(stripe.APIError):
            capture(hold.pk, 12_000, charge=Mock())
        with pytest.raises(stripe.APIError):
            capture(hold.pk, 12_000, charge=Mock())
        (difference_id,) = [
            pid
            for pid, data in fake_stripe.intents.items()
            if data["metadata"].get("kind") == "difference"
        ]
        assert fake_stripe.status_of(difference_id) == "succeeded"

        assert reconcile_payment_intent(hold.pk, difference_id) == "recorded"
        result = capture(hold.pk, 12_000, charge=Mock())

        assert result.status == CaptureStatus.PAID
        assert reloaded(hold).difference_payment_intent_id == difference_id
        assert signals["status"] == [("unpaid", "paid")]

    def test_a_reused_key_keeps_the_claim(self, order, fake_stripe) -> None:
        hold = live_hold(fake_stripe, target=order)
        fake_stripe.fail_next("PaymentIntent.create", idempotency_error())

        with pytest.raises(stripe.IdempotencyError):
            capture(hold.pk, 12_000, charge=Mock())

        assert reloaded(hold).difference_key == difference_idempotency_key(hold.pk)

    def test_a_409_keeps_the_claim(self, order, fake_stripe) -> None:
        hold = live_hold(fake_stripe, target=order)
        conflict = stripe.InvalidRequestError("in progress", None, http_status=409)
        fake_stripe.fail_next("PaymentIntent.create", conflict)

        with pytest.raises(stripe.InvalidRequestError):
            capture(hold.pk, 12_000, charge=Mock())

        assert reloaded(hold).difference_key == difference_idempotency_key(hold.pk)

    def test_a_claim_older_than_stripe_keeps_its_key_is_reconciled_not_replayed(
        self, order, fake_stripe
    ) -> None:
        hold = live_hold(fake_stripe, target=order)
        fake_stripe.fail_behind_next()
        with pytest.raises(stripe.APIError):
            capture(hold.pk, 12_000, charge=Mock())
        CardHold.objects.filter(pk=hold.pk).update(
            difference_claimed_at=timezone.now() - CHARGE_KEY_TTL - datetime.timedelta(hours=1)
        )
        fake_stripe.prune_keys()

        result = capture(hold.pk, 12_000, charge=Mock())

        assert result.status == CaptureStatus.PAID
        assert len(differences(fake_stripe)) == 1
        assert reloaded(hold).payment_status == CardHold.PaymentStatus.PAID

    def test_a_stale_claim_with_nothing_in_stripe_is_charged_with_a_new_key(
        self, order, fake_stripe
    ) -> None:
        hold = live_hold(fake_stripe, target=order)
        fake_stripe.fail_next("PaymentIntent.create", connection_error())
        with pytest.raises(stripe.APIConnectionError):
            capture(hold.pk, 12_000, charge=Mock())
        CardHold.objects.filter(pk=hold.pk).update(
            difference_claimed_at=timezone.now() - CHARGE_KEY_TTL - datetime.timedelta(hours=1)
        )

        result = capture(hold.pk, 12_000, charge=Mock())

        assert result.status == CaptureStatus.PAID
        keys = [params["idempotency_key"] for params in differences(fake_stripe)]
        assert keys == [
            difference_idempotency_key(hold.pk, 0),
            difference_idempotency_key(hold.pk, 1),
        ]

    def test_a_stale_claim_whose_lookup_fails_waits(self, order, fake_stripe) -> None:
        hold = live_hold(fake_stripe, target=order)
        fake_stripe.fail_next("PaymentIntent.create", connection_error())
        with pytest.raises(stripe.APIConnectionError):
            capture(hold.pk, 12_000, charge=Mock())
        CardHold.objects.filter(pk=hold.pk).update(
            difference_claimed_at=timezone.now() - CHARGE_KEY_TTL - datetime.timedelta(hours=1)
        )
        fake_stripe.fail_next("PaymentIntent.search", api_error())

        result = capture(hold.pk, 12_000, charge=Mock())

        assert result.status == CaptureStatus.IN_PROGRESS
        assert len(differences(fake_stripe)) == 1

    def test_a_stale_claim_found_declined_is_partially_paid(
        self, order, fake_stripe, signals
    ) -> None:
        hold = live_hold(fake_stripe, target=order)
        fake_stripe.fail_behind_next()
        with pytest.raises(stripe.APIError):
            capture(hold.pk, 12_000, charge=Mock())
        (difference_id,) = [
            pid for pid in fake_stripe.intents if pid != hold.stripe_payment_intent_id
        ]
        fake_stripe.set_status(difference_id, "requires_payment_method")
        CardHold.objects.filter(pk=hold.pk).update(
            difference_claimed_at=timezone.now() - CHARGE_KEY_TTL - datetime.timedelta(hours=1)
        )

        result = capture(hold.pk, 12_000, charge=Mock())

        assert result.status == CaptureStatus.PARTIALLY_PAID
        assert len(signals["failed"]) == 1

    def test_a_processing_difference_waits_for_the_webhook(self, order, fake_stripe) -> None:
        hold = live_hold(fake_stripe, target=order)
        fake_stripe.next_outcome.append("processing")

        result = capture(hold.pk, 12_000, charge=Mock())

        assert result.status == CaptureStatus.IN_PROGRESS
        hold = reloaded(hold)
        assert hold.difference_key and hold.payment_status == CardHold.PaymentStatus.UNPAID
        fake_stripe.set_status(result.payment_intent.id, "succeeded")
        fake_stripe.intents[result.payment_intent.id]["amount_received"] = 1_000
        assert reconcile_payment_intent(hold.pk, result.payment_intent.id) == "recorded"
        assert reloaded(hold).payment_status == CardHold.PaymentStatus.PAID

    def test_a_concurrent_claim_answers_in_progress(self, order, fake_stripe) -> None:
        hold = live_hold(fake_stripe, target=order)
        with patch("baseapp_payments.holds._claim_difference", return_value=False):
            result = capture(hold.pk, 12_000, charge=Mock())

        assert result.status == CaptureStatus.IN_PROGRESS
        assert differences(fake_stripe) == []

    def test_a_row_that_moved_before_the_plan_answers_in_progress(self, order, fake_stripe) -> None:
        hold = live_hold(fake_stripe, target=order)
        real_filter = CardHold.objects.filter

        def moved(*args: Any, **kwargs: Any) -> Any:
            if (
                kwargs.get("status") == CardHold.Status.AUTHORIZED
                and "stripe_payment_intent_id" in kwargs
            ):
                return real_filter(pk=-1)
            return real_filter(*args, **kwargs)

        with patch.object(CardHold.objects, "filter", side_effect=moved):
            result = capture(hold.pk, 12_000, charge=Mock())

        assert result.status == CaptureStatus.IN_PROGRESS
        assert fake_stripe.captures == []

    def test_a_planned_difference_is_dropped_by_a_capture_within_the_hold(
        self, order, fake_stripe
    ) -> None:
        hold = live_hold(fake_stripe, target=order)
        CardHold.objects.filter(pk=hold.pk).update(difference_amount_cents=1_000)

        result = capture(hold.pk, 10_000, charge=Mock())

        assert result.status == CaptureStatus.CAPTURED
        hold = reloaded(hold)
        assert hold.difference_amount_cents is None
        assert hold.payment_status == CardHold.PaymentStatus.PAID


class TestReconciliation:
    def test_the_difference_is_never_cancelled_as_a_stray(self, order, fake_stripe) -> None:
        hold = live_hold(fake_stripe, target=order)
        capture(hold.pk, 12_000, charge=Mock())
        difference_id = reloaded(hold).difference_payment_intent_id

        assert reconcile_payment_intent(hold.pk, difference_id) == "current"
        assert reloaded(hold).stray_payment_intent_ids == []
        assert fake_stripe.calls_to("PaymentIntent.cancel") == []

    def test_a_webhook_records_a_decline_of_the_outstanding_difference(
        self, order, fake_stripe, signals
    ) -> None:
        hold = live_hold(fake_stripe, target=order)
        fake_stripe.fail_behind_next()
        with pytest.raises(stripe.APIError):
            capture(hold.pk, 12_000, charge=Mock())
        (difference_id,) = [
            pid for pid in fake_stripe.intents if pid != hold.stripe_payment_intent_id
        ]
        fake_stripe.set_status(difference_id, "requires_payment_method")

        assert reconcile_payment_intent(hold.pk, difference_id) == "declined"
        assert reconcile_payment_intent(hold.pk, difference_id) == "ignored"

        assert reloaded(hold).payment_status == CardHold.PaymentStatus.PARTIALLY_PAID
        assert len(signals["failed"]) == 1

    def test_an_old_keys_difference_is_ignored(self, order, fake_stripe) -> None:
        hold = live_hold(fake_stripe, target=order)
        fake_stripe.next_outcome.append("card_declined")
        capture(hold.pk, 12_000, charge=Mock())
        (declined_id,) = [
            pid for pid in fake_stripe.intents if pid != hold.stripe_payment_intent_id
        ]

        assert reconcile_payment_intent(hold.pk, declined_id) == "ignored"
        assert fake_stripe.calls_to("PaymentIntent.cancel") == []

    def test_a_second_succeeded_difference_is_logged(self, order, fake_stripe, caplog) -> None:
        hold = live_hold(fake_stripe, target=order)
        capture(hold.pk, 12_000, charge=Mock())
        other = fake_stripe.PaymentIntent.create(
            amount=1_000,
            currency="usd",
            customer=STRIPE_CUSTOMER_ID,
            payment_method="pm_visa",
            confirm=True,
            metadata={"card_hold_id": str(hold.pk), "kind": "difference"},
        )

        assert reconcile_payment_intent(hold.pk, other.id) == "ignored"
        assert "check Stripe" in caplog.text

    def test_through_the_webhook_endpoint(self, client, settings, order, fake_stripe) -> None:
        from ..fakes import WEBHOOK_SECRET, deliver_event

        settings.STRIPE_WEBHOOK_SECRET = WEBHOOK_SECRET
        hold = live_hold(fake_stripe, target=order)
        fake_stripe.next_outcome.append("processing")
        result = capture(hold.pk, 12_000, charge=Mock())
        fake_stripe.set_status(result.payment_intent.id, "succeeded")

        response = deliver_event(
            client, fake_stripe.event("payment_intent.succeeded", result.payment_intent.id)
        )

        assert response.status_code == 200
        assert reloaded(hold).payment_status == CardHold.PaymentStatus.PAID


class TestFees:
    def test_fees_not_ready_are_filled_in_by_the_sweep(self, order, fake_stripe) -> None:
        from baseapp_payments.tasks import sweep_card_holds

        hold = live_hold(fake_stripe, target=order)
        fake_stripe.balance_ready = False
        capture(hold.pk, 12_000, charge=Mock())
        hold = reloaded(hold)
        assert hold.capture_fee_cents is None and hold.difference_fee_cents is None

        fake_stripe.balance_ready = True
        CardHold.objects.filter(pk=hold.pk).update(
            modified=timezone.now() - datetime.timedelta(hours=1)
        )
        sweep_card_holds()

        hold = reloaded(hold)
        assert hold.capture_fee_cents == FakeStripe.fee_for(HELD)
        assert hold.difference_fee_cents == FakeStripe.fee_for(1_000)
        retrieves = fake_stripe.calls_to("PaymentIntent.retrieve")
        assert all(
            params == {"expand": ["latest_charge.balance_transaction"]} for _a, params in retrieves
        )

    def test_the_sweep_leaves_paid_fees_and_old_payments_alone(self, order, fake_stripe) -> None:
        from baseapp_payments.tasks import sweep_card_holds

        hold = live_hold(fake_stripe, target=order)
        capture(hold.pk, 10_000, charge=Mock())
        fake_stripe.calls.clear()
        CardHold.objects.filter(pk=hold.pk).update(
            modified=timezone.now() - datetime.timedelta(hours=1)
        )

        sweep_card_holds()

        assert fake_stripe.calls_to("PaymentIntent.retrieve") == []

    def test_record_fees_skips_what_stripe_cant_find(self, order, fake_stripe, caplog) -> None:
        hold = CardHoldFactory(
            target=order,
            status=CardHold.Status.CAPTURED,
            captured_amount_cents=10_000,
            captured_at=timezone.now(),
        )

        assert record_fees(hold.pk) == 0
        assert record_fees(987_654) == 0
        assert "Could not read PaymentIntent" in caplog.text

    def test_the_fee_task_retries_through_the_sweep(self, order, fake_stripe, caplog) -> None:
        from baseapp_payments.tasks import record_card_hold_fees

        hold = live_hold(fake_stripe, target=order)
        fake_stripe.balance_ready = False
        capture(hold.pk, 10_000, charge=Mock())
        fake_stripe.fail_next("PaymentIntent.retrieve", connection_error())

        record_card_hold_fees(hold.pk)

        assert "the sweep retries" in caplog.text
        assert reloaded(hold).capture_fee_cents is None

    def test_without_stripe_the_fee_task_does_nothing(self, order, no_stripe_key) -> None:
        from baseapp_payments.tasks import record_card_hold_fees

        with patch("baseapp_payments.holds.record_fees") as record:
            record_card_hold_fees(1)

        record.assert_not_called()


class TestInvoice:
    def test_both_payments_are_recorded_on_one_invoice(self, order, fake_stripe) -> None:
        hold = live_hold(fake_stripe, target=order)
        capture(hold.pk, 12_000, charge=Mock())
        fake_stripe.add_invoice("in_order", amount_due=12_000)

        attached = attach_payments_to_invoice(hold.pk, "in_order")

        hold = reloaded(hold)
        assert attached == [hold.stripe_payment_intent_id, hold.difference_payment_intent_id]
        invoice = fake_stripe.invoices["in_order"]
        assert invoice["status"] == "paid"
        assert invoice["amount_paid"] == 12_000
        keys = [
            params["idempotency_key"]
            for _a, params in fake_stripe.calls_to("Invoice.attach_payment")
        ]
        assert keys == [f"testproject-invoice-in_order-{pid}" for pid in attached]

    def test_attaching_again_skips_what_is_on_the_invoice(self, order, fake_stripe) -> None:
        hold = live_hold(fake_stripe, target=order)
        capture(hold.pk, 12_000, charge=Mock())
        fake_stripe.add_invoice("in_order", amount_due=12_000)
        attach_payments_to_invoice(hold.pk, "in_order")

        again = attach_payments_to_invoice(hold.pk, "in_order")

        assert len(again) == 2
        assert len(fake_stripe.calls_to("Invoice.attach_payment")) == 2

    def test_a_single_full_charge_is_one_payment(self, order, fake_stripe) -> None:
        hold = CardHoldFactory(
            target=order, status=CardHold.Status.SAVED, stripe_payment_intent_id=None
        )
        capture(hold.pk, 12_000, charge=project_charge(fake_stripe, amount=12_000))
        fake_stripe.add_invoice("in_order", amount_due=12_000)

        assert attach_payments_to_invoice(hold.pk, "in_order") == [
            reloaded(hold).charge_payment_intent_id
        ]
        assert fake_stripe.invoices["in_order"]["status"] == "paid"

    def test_a_hold_with_no_payment_attaches_nothing(self, order, fake_stripe) -> None:
        hold = live_hold(fake_stripe, target=order)

        assert attach_payments_to_invoice(hold.pk, "in_order") == []
        assert fake_stripe.calls == []

    def test_stripes_refusal_propagates(self, order, fake_stripe) -> None:
        hold = live_hold(fake_stripe, target=order)
        capture(hold.pk, 12_000, charge=Mock())
        fake_stripe.add_invoice("in_order", amount_due=12_000, status="draft")

        with pytest.raises(stripe.InvalidRequestError):
            attach_payments_to_invoice(hold.pk, "in_order")


class TestMarkPaidOutside:
    @pytest.mark.parametrize(
        "fields",
        [
            {"payment_status": "unpaid"},
            {"payment_status": "paid"},
            {"payment_status": "partially_paid", "difference_key": "k"},
            {"payment_status": "partially_paid", "capture_claimed_at": timezone.now()},
        ],
        ids=["unpaid", "paid", "being_charged", "being_captured"],
    )
    def test_only_a_partially_paid_hold_no_one_is_charging(self, order, fields) -> None:
        if "capture_claimed_at" in fields:
            fields = {**fields, "capture_claimed_at": timezone.now()}
        hold = CardHoldFactory(target=order, status=CardHold.Status.CAPTURED, **fields)

        assert mark_paid_outside(hold.pk) is False
        assert reloaded(hold).paid_outside_at is None


class TestEdges:
    """Guards a race or a stray answer reaches; each must charge nothing extra."""

    def captured(self, order: Any, **fields: Any) -> Any:
        return CardHoldFactory(
            target=order,
            status=CardHold.Status.CAPTURED,
            captured_amount_cents=HELD,
            captured_at=timezone.now(),
            difference_amount_cents=1_000,
            **fields,
        )

    def test_an_unlinked_hold_is_never_charged_again_after_a_decline(self, fake_stripe) -> None:
        hold = CardHoldFactory(
            status=CardHold.Status.CAPTURED,
            captured_amount_cents=HELD,
            difference_amount_cents=1_000,
            difference_generation=1,
            payment_status=CardHold.PaymentStatus.PARTIALLY_PAID,
        )

        assert capture(hold.pk, 12_000, charge=Mock()).status == CaptureStatus.PARTIALLY_PAID
        assert fake_stripe.calls == []

    def test_charging_a_paid_or_unclaimed_difference_does_nothing(self, order, fake_stripe) -> None:
        from baseapp_payments.holds import _charge_difference

        paid = self.captured(order, payment_status=CardHold.PaymentStatus.PAID)
        unclaimed = self.captured(HoldableOrderFactory(user=order.user))

        assert _charge_difference(paid.pk).status == CaptureStatus.PAID
        assert _charge_difference(unclaimed.pk).status == CaptureStatus.NOT_CAPTURED
        assert fake_stripe.calls == []

    def test_recording_with_a_key_that_moved_on_changes_nothing(self, order, signals) -> None:
        from baseapp_payments.holds import _difference_refused, _record_difference

        hold = self.captured(order, difference_key="testproject-difference-x-1")
        intent = {"id": "pi_other", "latest_charge": {"balance_transaction": {"fee": 59}}}

        assert _record_difference(hold.pk, "testproject-difference-x-0", intent) is False
        assert _difference_refused(hold.pk, "testproject-difference-x-0", "card_declined") is False
        assert signals == {"status": [], "failed": []}

    def test_a_fee_without_a_currency_keeps_the_recorded_one(self, order) -> None:
        from baseapp_payments.holds import _record_difference, _store_fee

        hold = self.captured(order, difference_key="k", fee_currency="eur")
        intent = {"id": "pi_d", "latest_charge": {"balance_transaction": {"fee": 59}}}

        assert _store_fee(hold.pk, "capture_fee_cents", intent) is True
        assert _record_difference(hold.pk, "k", intent) is True
        hold = reloaded(hold)
        assert (hold.capture_fee_cents, hold.difference_fee_cents) == (59, 59)
        assert hold.fee_currency == "eur"

    def stale(self, order: Any, fake_stripe: FakeStripe, status: str) -> Any:
        hold = self.captured(order)
        key = difference_idempotency_key(hold.pk)
        CardHold.objects.filter(pk=hold.pk).update(
            difference_key=key,
            difference_claimed_at=timezone.now() - CHARGE_KEY_TTL - datetime.timedelta(hours=1),
        )
        fake_stripe.intents["pi_found"] = {
            "id": "pi_found",
            "object": "payment_intent",
            "status": status,
            "amount": 1_000,
            "currency": "usd",
            "customer": STRIPE_CUSTOMER_ID,
            "metadata": {"card_hold_id": str(hold.pk), "kind": "difference", "difference_key": key},
            "payment_method": "pm_visa",
            "capture_before": None,
            "amount_received": 0,
            "created": 0,
        }
        return hold

    def test_a_stale_claim_found_processing_waits(self, order, fake_stripe) -> None:
        hold = self.stale(order, fake_stripe, "processing")

        assert capture(hold.pk, 12_000, charge=Mock()).status == CaptureStatus.IN_PROGRESS
        assert fake_stripe.calls_to("PaymentIntent.create") == []

    @pytest.mark.parametrize("step", ["rotate", "claim"])
    def test_a_stale_claim_rotated_by_someone_else_waits(self, order, fake_stripe, step) -> None:
        hold = self.captured(order)
        CardHold.objects.filter(pk=hold.pk).update(
            difference_key=difference_idempotency_key(hold.pk),
            difference_claimed_at=timezone.now() - CHARGE_KEY_TTL - datetime.timedelta(hours=1),
        )
        target = "baseapp_payments.holds._claim_difference"
        with (
            patch(target, return_value=False)
            if step == "claim"
            else patch(
                "baseapp_payments.holds.find_difference_payment_intents",
                side_effect=lambda h: CardHold.objects.filter(pk=h.pk).update(difference_key="")
                and [],
            )
        ):
            result = capture(hold.pk, 12_000, charge=Mock())

        assert result.status == CaptureStatus.IN_PROGRESS
        assert fake_stripe.calls_to("PaymentIntent.create") == []

    def test_a_webhook_for_a_paid_hold_or_an_undecided_difference_is_ignored(
        self, order, fake_stripe
    ) -> None:
        from baseapp_payments.holds import _apply_difference

        key = "testproject-difference-1-0"
        intent = {"id": "pi_x", "status": "processing", "metadata": {"difference_key": key}}
        charged = self.captured(order, difference_charged_at=timezone.now())
        claimed = self.captured(HoldableOrderFactory(user=order.user), difference_key=key)

        assert _apply_difference(charged, {**intent, "status": "requires_payment_method"}) == (
            "ignored"
        )
        assert _apply_difference(claimed, intent) == "ignored"
        assert reloaded(claimed).difference_key == key

    def test_record_fees_skips_a_charge_with_no_payment_intent(self, order, fake_stripe) -> None:
        hold = CardHoldFactory(target=order, status=CardHold.Status.RELEASED)
        CardHold.objects.filter(pk=hold.pk).update(charged_at=timezone.now())

        assert record_fees(hold.pk) == 0
        assert fake_stripe.calls == []


def authorizations_only(hold: Any) -> list[Any]:
    """A project's ``BASEAPP_PAYMENTS_CARD_HOLD_LOOKUP`` written for authorizations: it
    returns only manual-capture PaymentIntents still holding money."""
    from baseapp_payments.holds import find_hold_payment_intents

    return [pi for pi in find_hold_payment_intents(hold) if pi["status"] == "requires_capture"]


def stale_claim(hold: Any) -> None:
    CardHold.objects.filter(pk=hold.pk).update(
        difference_claimed_at=timezone.now() - CHARGE_KEY_TTL - datetime.timedelta(hours=1)
    )


def lose_capture_answers(fake_stripe: FakeStripe) -> Any:
    """Every capture reaches Stripe and runs, but its answer is lost."""
    real_capture = fake_stripe.PaymentIntent.capture

    def lost(payment_intent_id: str, **params: Any) -> Any:
        real_capture(payment_intent_id, **params)
        raise connection_error()

    return patch.object(fake_stripe.PaymentIntent, "capture", side_effect=lost)


class TestStaleDifferenceLookup:
    def test_a_project_lookup_for_authorizations_never_charges_it_twice(
        self, order, fake_stripe, settings
    ) -> None:
        """The difference charged behind a 5xx, its key past Stripe's 24 hours: the
        project's lookup can't see it, the module's own Search on its key does."""
        settings.BASEAPP_PAYMENTS_CARD_HOLD_LOOKUP = f"{__name__}.authorizations_only"
        hold = live_hold(fake_stripe, target=order)
        fake_stripe.fail_behind_next()
        with pytest.raises(stripe.APIError):
            capture(hold.pk, 12_000, charge=Mock())
        stale_claim(hold)
        fake_stripe.prune_keys()

        result = capture(hold.pk, 12_000, charge=Mock())

        assert result.status == CaptureStatus.PAID
        assert len(differences(fake_stripe)) == 1
        queries = [params["query"] for _a, params in fake_stripe.calls_to("PaymentIntent.search")]
        assert queries == [f"metadata['difference_key']:'{difference_idempotency_key(hold.pk)}'"]
        assert reloaded(hold).payment_status == CardHold.PaymentStatus.PAID

    def test_where_search_is_refused_the_customers_payments_are_listed(
        self, order, fake_stripe
    ) -> None:
        hold = live_hold(fake_stripe, target=order)
        fake_stripe.fail_behind_next()
        with pytest.raises(stripe.APIError):
            capture(hold.pk, 12_000, charge=Mock())
        stale_claim(hold)
        fake_stripe.prune_keys()
        fake_stripe.fail_next(
            "PaymentIntent.search", stripe.InvalidRequestError("Search isn't available", None)
        )

        result = capture(hold.pk, 12_000, charge=Mock())

        assert result.status == CaptureStatus.PAID
        assert len(differences(fake_stripe)) == 1
        ((_args, listed),) = fake_stripe.calls_to("PaymentIntent.list")
        assert listed["customer"] == STRIPE_CUSTOMER_ID

    def test_without_a_customer_nothing_is_listed(self, order, fake_stripe) -> None:
        from baseapp_payments.holds import find_difference_payment_intents

        hold = CardHoldFactory(target=order, stripe_customer_id="", difference_key="k")
        fake_stripe.fail_next("PaymentIntent.search", stripe.InvalidRequestError("No", None))

        assert find_difference_payment_intents(hold) == []
        assert fake_stripe.calls_to("PaymentIntent.list") == []


class TestAmountChangedAfterALostCapture:
    """The whole hold's capture ran but its answer was lost; the next call asks less."""

    def test_the_overcharge_is_never_marked_paid(self, order, fake_stripe, signals, caplog) -> None:
        from baseapp_payments.tasks import sweep_card_holds

        hold = live_hold(fake_stripe, target=order)
        payment_intent_id = hold.stripe_payment_intent_id
        with lose_capture_answers(fake_stripe), pytest.raises(stripe.APIConnectionError):
            capture(hold.pk, 12_000, charge=Mock())
        assert fake_stripe.captures == [(payment_intent_id, HELD)]

        lower = capture(hold.pk, 10_000, charge=Mock())

        assert lower.status == CaptureStatus.NOT_CAPTURED
        assert isinstance(lower.error, stripe.IdempotencyError)
        hold = reloaded(hold)
        # The full-hold capture may have run: its plan is kept.
        assert hold.difference_amount_cents == 1_000
        assert hold.requested_amount_cents == 10_000
        assert hold.capture_sent_at is not None

        # The webhook brings the first capture's answer.
        assert reconcile_payment_intent(hold.pk, payment_intent_id) == "captured"

        hold = reloaded(hold)
        assert hold.status == CardHold.Status.CAPTURED
        assert hold.captured_amount_cents == HELD
        assert hold.payment_status == CardHold.PaymentStatus.UNPAID
        assert "not marked paid" in caplog.text
        assert signals == {"status": [], "failed": []}
        # Nothing charges the difference on top: not a retry, not the sweep.
        assert capture(hold.pk, 10_000, charge=Mock()).status == CaptureStatus.NOT_CAPTURED
        CardHold.objects.filter(pk=hold.pk).update(
            captured_at=timezone.now() - datetime.timedelta(hours=1)
        )
        sweep_card_holds()
        assert differences(fake_stripe) == []
        assert reloaded(hold).payment_status == CardHold.PaymentStatus.UNPAID

    def test_asked_for_the_held_amount_the_replay_is_paid(
        self, order, fake_stripe, signals
    ) -> None:
        hold = live_hold(fake_stripe, target=order)
        with lose_capture_answers(fake_stripe), pytest.raises(stripe.APIConnectionError):
            capture(hold.pk, 12_000, charge=Mock())

        result = capture(hold.pk, HELD, charge=Mock())

        assert result.status == CaptureStatus.CAPTURED
        assert len(fake_stripe.captures) == 1
        hold = reloaded(hold)
        assert hold.payment_status == CardHold.PaymentStatus.PAID
        assert hold.difference_amount_cents is None
        assert differences(fake_stripe) == []
        assert signals["status"] == [("unpaid", "paid")]

    def test_a_capture_that_never_reached_stripe_takes_the_lower_amount(
        self, order, fake_stripe, signals
    ) -> None:
        hold = live_hold(fake_stripe, target=order)
        fake_stripe.fail_next("PaymentIntent.capture", connection_error())
        with pytest.raises(stripe.APIConnectionError):
            capture(hold.pk, 12_000, charge=Mock())

        result = capture(hold.pk, 10_000, charge=Mock())

        assert result.status == CaptureStatus.CAPTURED
        assert fake_stripe.captures == [(hold.stripe_payment_intent_id, 10_000)]
        hold = reloaded(hold)
        assert hold.payment_status == CardHold.PaymentStatus.PAID
        assert hold.difference_amount_cents is None
        assert differences(fake_stripe) == []

    def test_a_capture_answered_for_another_amount_within_the_hold_stays_unpaid(
        self, order, fake_stripe, caplog
    ) -> None:
        from baseapp_payments.holds import mark_captured

        hold = live_hold(fake_stripe, target=order)
        CardHold.objects.filter(pk=hold.pk).update(
            requested_amount_cents=9_000, capture_sent_at=timezone.now()
        )

        assert mark_captured(hold.pk, amount_cents=10_000) is True

        assert reloaded(hold).payment_status == CardHold.PaymentStatus.UNPAID
        assert "not marked paid" in caplog.text


class TestDifferenceNeverRetried:
    """capture() stopped coming back after the hold was captured: the sweep finishes it."""

    def abandoned(self, order: Any, fake_stripe: FakeStripe, **after: Any) -> Any:
        hold = live_hold(fake_stripe, target=order)
        with patch("baseapp_payments.holds._claim_difference", side_effect=RuntimeError("died")):
            with pytest.raises(RuntimeError):
                capture(hold.pk, 12_000, charge=Mock())
        CardHold.objects.filter(pk=hold.pk).update(
            **{"captured_at": timezone.now() - datetime.timedelta(hours=1), **after}
        )
        return hold

    def test_the_sweep_charges_the_difference_once(self, order, fake_stripe, signals) -> None:
        from baseapp_payments.tasks import sweep_card_holds

        hold = self.abandoned(order, fake_stripe)

        sweep_card_holds()
        sweep_card_holds()

        assert len(differences(fake_stripe)) == 1
        assert len(fake_stripe.captures) == 1
        hold = reloaded(hold)
        assert hold.payment_status == CardHold.PaymentStatus.PAID
        assert hold.capture_claimed_at is None
        assert signals["status"] == [("unpaid", "paid")]

    def test_a_claim_left_without_an_answer_is_resumed_with_its_key(
        self, order, fake_stripe
    ) -> None:
        from baseapp_payments.tasks import sweep_card_holds

        hold = live_hold(fake_stripe, target=order)
        fake_stripe.fail_next("PaymentIntent.create", connection_error())
        with pytest.raises(stripe.APIConnectionError):
            capture(hold.pk, 12_000, charge=Mock())
        old = timezone.now() - datetime.timedelta(hours=1)
        CardHold.objects.filter(pk=hold.pk).update(captured_at=old, difference_claimed_at=old)

        sweep_card_holds()

        keys = {params["idempotency_key"] for params in differences(fake_stripe)}
        assert keys == {difference_idempotency_key(hold.pk)}
        assert reloaded(hold).payment_status == CardHold.PaymentStatus.PAID

    def test_a_cancelled_target_is_left_for_a_person(self, order, fake_stripe, caplog) -> None:
        from baseapp_payments.tasks import sweep_card_holds

        hold = self.abandoned(order, fake_stripe)
        HoldableOrder.objects.filter(pk=order.pk).update(status=HoldableOrder.Status.CANCELLED)

        sweep_card_holds()

        assert differences(fake_stripe) == []
        hold = reloaded(hold)
        assert hold.payment_status == CardHold.PaymentStatus.UNPAID
        assert hold.charge_blocked_reason == CardHold.ChargeBlock.TARGET_CANCELLED
        assert caplog.text.count("Decide by hand") == 1

        # Marked, it is never queued again, and logged once.
        with patch("baseapp_payments.holds.charge_due_difference") as charge_due:
            sweep_card_holds()
        charge_due.assert_not_called()
        from baseapp_payments.holds import charge_due_difference

        assert charge_due_difference(hold.pk).status == CaptureStatus.NOT_CAPTURED
        assert caplog.text.count("Decide by hand") == 1

    def test_a_cancelled_target_stops_a_resumed_claim_too(self, order, fake_stripe, caplog) -> None:
        from baseapp_payments.holds import _difference_target_cancelled, charge_due_difference

        old = timezone.now() - datetime.timedelta(hours=1)
        hold = self.abandoned(order, fake_stripe, difference_key="k", difference_claimed_at=old)
        HoldableOrder.objects.filter(pk=order.pk).update(status=HoldableOrder.Status.CANCELLED)

        assert charge_due_difference(hold.pk).status == CaptureStatus.NOT_CAPTURED
        assert _difference_target_cancelled(reloaded(hold)).status == CaptureStatus.NOT_CAPTURED

        assert differences(fake_stripe) == []
        assert reloaded(hold).charge_blocked_reason == CardHold.ChargeBlock.TARGET_CANCELLED
        assert caplog.text.count("Decide by hand") == 1

    def test_a_cancelled_target_can_still_be_settled_by_hand(
        self, order, fake_stripe, signals
    ) -> None:
        """The marker stops the sweep only: the project's capture() still charges the
        difference, and a refused one can still be marked paid outside."""
        from baseapp_payments.tasks import sweep_card_holds

        hold = self.abandoned(order, fake_stripe)
        HoldableOrder.objects.filter(pk=order.pk).update(status=HoldableOrder.Status.CANCELLED)
        sweep_card_holds()
        fake_stripe.next_outcome.append("requires_payment_method")

        refused = capture(hold.pk, 12_000, charge=Mock())

        assert refused.status == CaptureStatus.PARTIALLY_PAID
        assert len(differences(fake_stripe)) == 1
        assert mark_paid_outside(hold.pk) is True
        assert reloaded(hold).payment_status == CardHold.PaymentStatus.PAID

    def test_a_cancelled_target_is_paid_by_a_manual_capture(self, order, fake_stripe) -> None:
        from baseapp_payments.tasks import sweep_card_holds

        hold = self.abandoned(order, fake_stripe)
        HoldableOrder.objects.filter(pk=order.pk).update(status=HoldableOrder.Status.CANCELLED)
        sweep_card_holds()

        assert capture(hold.pk, 12_000, charge=Mock()).status == CaptureStatus.PAID
        assert len(differences(fake_stripe)) == 1

    @pytest.mark.parametrize(
        "after",
        [
            {"captured_at": timezone.now()},
            {"payment_status": "partially_paid"},
            {"capture_claimed_at": timezone.now()},
            {"difference_key": "k", "difference_claimed_at": timezone.now()},
            {"requested_amount_cents": 13_000},
        ],
        ids=["just_captured", "refused", "capture_running", "claim_live", "other_amount"],
    )
    def test_the_sweep_leaves_what_isnt_its_to_charge(self, order, fake_stripe, after) -> None:
        from baseapp_payments.tasks import sweep_card_holds

        after = {
            key: timezone.now() if key.endswith("_at") else value for key, value in after.items()
        }
        self.abandoned(order, fake_stripe, **after)

        with patch("baseapp_payments.holds.charge_due_difference") as charge_due:
            sweep_card_holds()

        charge_due.assert_not_called()

    def test_charging_it_directly_checks_what_is_due(self, order, fake_stripe) -> None:
        from baseapp_payments.holds import charge_due_difference

        hold = self.abandoned(order, fake_stripe, requested_amount_cents=13_000)
        claimed = self.abandoned(
            HoldableOrderFactory(user=order.user), fake_stripe, capture_claimed_at=timezone.now()
        )

        assert charge_due_difference(hold.pk).status == CaptureStatus.NOT_CAPTURED
        assert charge_due_difference(claimed.pk).status == CaptureStatus.IN_PROGRESS
        assert charge_due_difference(987_654).status == CaptureStatus.IN_PROGRESS
        assert differences(fake_stripe) == []

    def test_the_task_leaves_a_stripe_error_for_the_next_sweep(
        self, order, fake_stripe, caplog
    ) -> None:
        from baseapp_payments.tasks import charge_card_hold_difference

        hold = self.abandoned(order, fake_stripe)
        fake_stripe.fail_next("PaymentIntent.create", connection_error())

        charge_card_hold_difference(hold.pk)

        assert "the sweep retries" in caplog.text
        assert reloaded(hold).difference_key == difference_idempotency_key(hold.pk)

    def test_without_stripe_the_task_does_nothing(self, no_stripe_key) -> None:
        from baseapp_payments.tasks import charge_card_hold_difference

        with patch("baseapp_payments.holds.charge_due_difference") as charge_due:
            charge_card_hold_difference(1)

        charge_due.assert_not_called()


class TestProcessingDifference:
    @pytest.mark.parametrize("stale", [False, True], ids=["fresh", "past_the_key_ttl"])
    def test_it_is_read_back_not_replayed(self, order, fake_stripe, signals, stale) -> None:
        hold = live_hold(fake_stripe, target=order)
        fake_stripe.next_outcome.append("processing")
        waiting = capture(hold.pk, 12_000, charge=Mock())
        difference_id = waiting.payment_intent.id
        assert reloaded(hold).difference_payment_intent_id == difference_id
        if stale:
            stale_claim(hold)
        fake_stripe.set_status(difference_id, "succeeded")
        fake_stripe.intents[difference_id]["amount_received"] = 1_000

        result = capture(hold.pk, 12_000, charge=Mock())

        assert result.status == CaptureStatus.PAID
        assert len(differences(fake_stripe)) == 1
        assert fake_stripe.calls_to("PaymentIntent.search") == []
        retrieved = [args[0] for args, _p in fake_stripe.calls_to("PaymentIntent.retrieve")]
        assert retrieved == [difference_id]
        hold = reloaded(hold)
        assert hold.difference_fee_cents == FakeStripe.fee_for(1_000)
        assert signals["status"] == [("unpaid", "paid")]

    def test_still_processing_it_waits(self, order, fake_stripe) -> None:
        hold = live_hold(fake_stripe, target=order)
        fake_stripe.next_outcome.append("processing")
        capture(hold.pk, 12_000, charge=Mock())

        assert capture(hold.pk, 12_000, charge=Mock()).status == CaptureStatus.IN_PROGRESS
        assert len(differences(fake_stripe)) == 1

    def test_refused_later_the_next_charge_is_a_new_payment(
        self, order, fake_stripe, signals
    ) -> None:
        hold = live_hold(fake_stripe, target=order)
        fake_stripe.next_outcome.append("processing")
        waiting = capture(hold.pk, 12_000, charge=Mock())
        fake_stripe.set_status(waiting.payment_intent.id, "requires_payment_method")

        refused = capture(hold.pk, 12_000, charge=Mock())
        assert reloaded(hold).difference_payment_intent_id is None
        paid = capture(hold.pk, 12_000, charge=Mock())

        assert refused.status == CaptureStatus.PARTIALLY_PAID
        assert paid.status == CaptureStatus.PAID
        keys = [params["idempotency_key"] for params in differences(fake_stripe)]
        assert keys == [
            difference_idempotency_key(hold.pk, 0),
            difference_idempotency_key(hold.pk, 1),
        ]
        assert reloaded(hold).difference_payment_intent_id == paid.payment_intent.id


def test_a_refusal_recorded_meanwhile_answers_partially_paid(order, fake_stripe) -> None:
    """Another caller's refusal dropped the claim between reading and charging."""
    from baseapp_payments.holds import _charge_difference

    hold = CardHoldFactory(
        target=order,
        status=CardHold.Status.CAPTURED,
        captured_amount_cents=HELD,
        difference_amount_cents=1_000,
        difference_generation=1,
        payment_status=CardHold.PaymentStatus.PARTIALLY_PAID,
    )

    assert _charge_difference(hold.pk).status == CaptureStatus.PARTIALLY_PAID
    assert fake_stripe.calls == []


def test_the_invoice_helper_reads_every_page_of_payments(order, fake_stripe) -> None:
    hold = live_hold(fake_stripe, target=order)
    capture(hold.pk, 12_000, charge=Mock())
    fake_stripe.add_invoice("in_order", amount_due=12_000)
    attach_payments_to_invoice(hold.pk, "in_order")
    fake_stripe.invoice_page_size = 1

    again = attach_payments_to_invoice(hold.pk, "in_order")

    assert len(again) == 2
    # The second payment is on the second page: never attached twice.
    assert len(fake_stripe.calls_to("Invoice.attach_payment")) == 2
    pages = fake_stripe.calls_to("InvoicePayment.list")
    assert pages[-2:] == [
        ((), {"invoice": "in_order", "limit": 100}),
        ((), {"starting_after": f"inpay_in_order_{hold.stripe_payment_intent_id}"}),
    ]


class TestChargeTotals:
    def test_a_charge_that_returns_no_payment_intent_counts_the_amount_asked(
        self, order, fake_stripe
    ) -> None:
        hold = CardHoldFactory(
            target=order, status=CardHold.Status.SAVED, stripe_payment_intent_id=None
        )

        capture(hold.pk, 12_000, charge=Mock(return_value="ch_elsewhere"))

        totals = CardHold.objects.with_payment_totals().get(pk=hold.pk)
        assert totals.charge_amount_cents == 12_000
        assert totals.paid_cents == 12_000

    def test_a_refused_charge_drops_its_amount(self, order, fake_stripe) -> None:
        hold = CardHoldFactory(
            target=order, status=CardHold.Status.SAVED, stripe_payment_intent_id=None
        )

        declined = capture(hold.pk, 12_000, charge=Mock(side_effect=card_declined()))
        assert declined.status == CaptureStatus.DECLINED
        assert reloaded(hold).charge_amount_cents is None
        capture(hold.pk, 12_500, charge=Mock(return_value=None))

        totals = CardHold.objects.with_payment_totals().get(pk=hold.pk)
        assert totals.paid_cents == 12_500

    def test_a_resumed_charge_keeps_the_amount_its_key_was_sent_for(
        self, order, fake_stripe
    ) -> None:
        hold = CardHoldFactory(
            target=order, status=CardHold.Status.SAVED, stripe_payment_intent_id=None
        )
        with pytest.raises(stripe.APIConnectionError):
            capture(hold.pk, 12_000, charge=Mock(side_effect=connection_error()))

        capture(hold.pk, 12_500, charge=Mock(return_value=None))

        assert reloaded(hold).charge_amount_cents == 12_000


def captured_behind_the_webhook(order: Any, fake_stripe: FakeStripe, amount: int = 12_000) -> Any:
    """``capture(amount)`` sent the whole hold's capture, but its answer was lost; the
    webhook then recorded the capture of the hold."""
    hold = live_hold(fake_stripe, target=order)
    with lose_capture_answers(fake_stripe), pytest.raises(stripe.APIConnectionError):
        capture(hold.pk, amount, charge=Mock())
    assert reconcile_payment_intent(hold.pk, hold.stripe_payment_intent_id) == "captured"
    return reloaded(hold)


def age_capture(hold: Any) -> None:
    CardHold.objects.filter(pk=hold.pk).update(
        captured_at=timezone.now() - datetime.timedelta(hours=1)
    )


class TestLoweredAfterTheWebhook:
    """The webhook recorded the whole hold's capture first; then capture() asks less."""

    def test_asked_for_the_amount_captured_it_is_paid(self, order, fake_stripe, signals) -> None:
        from baseapp_payments.tasks import sweep_card_holds

        hold = captured_behind_the_webhook(order, fake_stripe)
        assert hold.payment_status == CardHold.PaymentStatus.UNPAID
        assert hold.difference_amount_cents == 1_000

        result = capture(hold.pk, HELD, charge=Mock())

        assert result.status == CaptureStatus.CAPTURED
        hold = reloaded(hold)
        assert hold.payment_status == CardHold.PaymentStatus.PAID
        assert hold.difference_amount_cents is None
        assert hold.requested_amount_cents == HELD
        assert signals["status"] == [("unpaid", "paid")]
        age_capture(hold)
        sweep_card_holds()
        assert differences(fake_stripe) == []
        assert len(fake_stripe.captures) == 1

    def test_asked_for_less_it_stays_unpaid_for_a_person(
        self, order, fake_stripe, signals, caplog
    ) -> None:
        from baseapp_payments.holds import charge_due_difference
        from baseapp_payments.tasks import sweep_card_holds

        hold = captured_behind_the_webhook(order, fake_stripe)

        result = capture(hold.pk, 10_000, charge=Mock())

        assert result.status == CaptureStatus.NOT_CAPTURED
        hold = reloaded(hold)
        assert hold.requested_amount_cents == 10_000
        assert hold.payment_status == CardHold.PaymentStatus.UNPAID
        assert "Settle it by hand" in caplog.text
        age_capture(hold)
        sweep_card_holds()
        assert charge_due_difference(hold.pk).status == CaptureStatus.NOT_CAPTURED
        assert differences(fake_stripe) == []
        assert reloaded(hold).payment_status == CardHold.PaymentStatus.UNPAID
        assert signals == {"status": [], "failed": []}

    def test_asked_for_the_planned_amount_again_the_difference_is_charged(
        self, order, fake_stripe
    ) -> None:
        hold = captured_behind_the_webhook(order, fake_stripe)
        capture(hold.pk, 10_000, charge=Mock())

        result = capture(hold.pk, 12_000, charge=Mock())

        assert result.status == CaptureStatus.PAID
        assert len(differences(fake_stripe)) == 1
        assert reloaded(hold).requested_amount_cents == 12_000

    def test_a_difference_already_claimed_keeps_its_ask(self, order, fake_stripe, caplog) -> None:
        """A claimed difference may have run: the lower ask is logged, never recorded."""
        hold = captured_behind_the_webhook(order, fake_stripe)
        CardHold.objects.filter(pk=hold.pk).update(difference_key="k")

        assert capture(hold.pk, HELD, charge=Mock()).status == CaptureStatus.NOT_CAPTURED

        hold = reloaded(hold)
        assert hold.requested_amount_cents == 12_000
        assert hold.payment_status == CardHold.PaymentStatus.UNPAID
        assert "Settle it by hand" in caplog.text


class TestCapturedWithoutAnAmount:
    """Stripe couldn't be read when the capture was recorded: no amount on the row."""

    def recorded_blind(self, order: Any, fake_stripe: FakeStripe, amount: int) -> Any:
        from baseapp_payments.holds import _record_capture_from_stripe

        hold = live_hold(fake_stripe, target=order)
        with lose_capture_answers(fake_stripe), pytest.raises(stripe.APIConnectionError):
            capture(hold.pk, amount, charge=Mock())
        fake_stripe.fail_next("PaymentIntent.retrieve", connection_error())
        _record_capture_from_stripe(hold.pk, hold.stripe_payment_intent_id)
        hold = reloaded(hold)
        assert hold.status == CardHold.Status.CAPTURED
        assert hold.captured_amount_cents is None
        # An amount was asked for: never paid before the amount taken is known.
        assert hold.payment_status == CardHold.PaymentStatus.UNPAID
        return hold

    @pytest.mark.parametrize("amount", [HELD, 12_000], ids=["within", "above"])
    def test_the_webhook_with_the_amount_completes_it(
        self, order, fake_stripe, signals, amount
    ) -> None:
        from baseapp_payments.tasks import sweep_card_holds

        hold = self.recorded_blind(order, fake_stripe, amount)

        assert reconcile_payment_intent(hold.pk, hold.stripe_payment_intent_id) == "captured"
        assert reloaded(hold).captured_amount_cents == HELD
        age_capture(hold)
        sweep_card_holds()

        hold = reloaded(hold)
        assert hold.payment_status == CardHold.PaymentStatus.PAID
        assert len(differences(fake_stripe)) == (1 if amount > HELD else 0)
        assert signals["status"] == [("unpaid", "paid")]

    def test_the_sweep_fills_in_the_amount(self, order, fake_stripe, signals) -> None:
        from baseapp_payments.tasks import sweep_card_holds

        hold = self.recorded_blind(order, fake_stripe, 12_000)
        age_capture(hold)

        sweep_card_holds()

        hold = reloaded(hold)
        assert hold.captured_amount_cents == HELD
        assert hold.payment_status == CardHold.PaymentStatus.PAID
        assert len(differences(fake_stripe)) == 1
        sweep_card_holds()
        assert len(differences(fake_stripe)) == 1

    def test_the_sweep_leaves_a_fresh_capture(self, order, fake_stripe) -> None:
        from baseapp_payments.tasks import sweep_card_holds

        self.recorded_blind(order, fake_stripe, 12_000)

        with patch("baseapp_payments.holds.record_captured_amount") as fill:
            sweep_card_holds()

        fill.assert_not_called()

    def test_an_unknown_amount_with_one_asked_is_never_paid(self, order) -> None:
        from baseapp_payments.holds import mark_captured

        hold = CardHoldFactory(
            target=order, requested_amount_cents=HELD, capture_sent_at=timezone.now()
        )

        mark_captured(hold.pk)
        mark_captured(hold.pk)

        hold = reloaded(hold)
        assert hold.status == CardHold.Status.CAPTURED
        assert hold.payment_status == CardHold.PaymentStatus.UNPAID

    def test_nothing_asked_and_nothing_planned_is_paid(self, order) -> None:
        from baseapp_payments.holds import mark_captured

        hold = CardHoldFactory(target=order)

        mark_captured(hold.pk)

        assert reloaded(hold).payment_status == CardHold.PaymentStatus.PAID

    def test_a_difference_planned_with_nothing_asked_is_not_paid(self, order) -> None:
        from baseapp_payments.holds import mark_captured

        hold = CardHoldFactory(target=order, difference_amount_cents=1_000)

        mark_captured(hold.pk, amount_cents=HELD)

        assert reloaded(hold).payment_status == CardHold.PaymentStatus.UNPAID

    def test_stripe_disagreeing_is_logged_not_filled(self, order, fake_stripe, caplog) -> None:
        from baseapp_payments.holds import record_captured_amount

        hold = live_hold(fake_stripe, target=order, status=CardHold.Status.CAPTURED)

        assert record_captured_amount(hold.pk) is False
        assert record_captured_amount(987_654) is False
        assert reloaded(hold).captured_amount_cents is None
        assert "Check Stripe" in caplog.text

    def test_the_task_leaves_a_stripe_error_for_the_next_sweep(
        self, order, fake_stripe, caplog
    ) -> None:
        from baseapp_payments.tasks import record_card_hold_capture

        hold = self.recorded_blind(order, fake_stripe, 12_000)
        fake_stripe.fail_next("PaymentIntent.retrieve", connection_error())

        record_card_hold_capture(hold.pk)

        assert "the sweep retries" in caplog.text
        assert reloaded(hold).captured_amount_cents is None

    def test_without_stripe_the_task_does_nothing(self, no_stripe_key) -> None:
        from baseapp_payments.tasks import record_card_hold_capture

        with patch("baseapp_payments.holds.record_captured_amount") as fill:
            record_card_hold_capture(1)

        fill.assert_not_called()


class TestTargetCheckAndClaimTogether:
    """The target's re-check and the difference's claim are one transaction."""

    def refused_once(self, order: Any, fake_stripe: FakeStripe) -> Any:
        hold = live_hold(fake_stripe, target=order)
        fake_stripe.next_outcome.append("requires_payment_method")
        assert capture(hold.pk, 12_000, charge=Mock()).status == CaptureStatus.PARTIALLY_PAID
        return hold

    def test_a_cancellation_committed_before_the_claim_charges_nothing(
        self, order, fake_stripe
    ) -> None:
        """The cancellation lands as the target is locked, just before the claim."""
        from baseapp_payments import holds

        hold = self.refused_once(order, fake_stripe)
        real = holds._why_not_holdable

        def cancelled_meanwhile(adapter: Any, target: Any) -> Any:
            HoldableOrder.objects.filter(pk=order.pk).update(status=HoldableOrder.Status.CANCELLED)
            target.refresh_from_db()
            return real(adapter, target)

        with patch.object(holds, "_why_not_holdable", side_effect=cancelled_meanwhile):
            result = capture(hold.pk, 12_000, charge=Mock())

        assert result.status == CaptureStatus.PARTIALLY_PAID
        assert len(differences(fake_stripe)) == 1
        assert reloaded(hold).difference_key == ""

    def test_the_claim_is_taken_under_the_target_lock(self, order, fake_stripe) -> None:
        from django.db import connection

        from baseapp_payments import holds

        hold = self.refused_once(order, fake_stripe)
        outside = len(connection.savepoint_ids)
        real = holds._claim_difference
        depths: list[int] = []

        def claim(claimed: Any) -> bool:
            depths.append(len(connection.savepoint_ids))
            return real(claimed)

        with patch.object(holds, "_claim_difference", side_effect=claim):
            assert capture(hold.pk, 12_000, charge=Mock()).status == CaptureStatus.PAID

        assert depths == [outside + 1]

    def test_the_sweep_claims_under_the_target_lock_too(self, order, fake_stripe) -> None:
        from baseapp_payments import holds
        from baseapp_payments.tasks import sweep_card_holds

        hold = live_hold(fake_stripe, target=order)
        with patch("baseapp_payments.holds._claim_difference", side_effect=RuntimeError("died")):
            with pytest.raises(RuntimeError):
                capture(hold.pk, 12_000, charge=Mock())
        age_capture(hold)
        real = holds._why_not_holdable

        def cancelled_meanwhile(adapter: Any, target: Any) -> Any:
            HoldableOrder.objects.filter(pk=order.pk).update(status=HoldableOrder.Status.CANCELLED)
            target.refresh_from_db()
            return real(adapter, target)

        with patch.object(holds, "_why_not_holdable", side_effect=cancelled_meanwhile):
            sweep_card_holds()

        assert differences(fake_stripe) == []
        assert reloaded(hold).charge_blocked_reason == CardHold.ChargeBlock.TARGET_CANCELLED
