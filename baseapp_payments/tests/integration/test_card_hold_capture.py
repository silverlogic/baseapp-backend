"""Capturing a hold (one charge, never two) and the card-removal guard."""

import datetime
import uuid
from typing import Any
from unittest.mock import Mock, patch

import pytest
import stripe
import swapper
from django.utils import timezone

from baseapp_payments.holds import (
    CaptureStatus,
    PlacementStatus,
    authorize_on_session,
    capturable_hold,
    capture,
    card_in_use,
    charge_idempotency_key,
    in_use_payment_method_ids,
    mark_captured,
    release_for_charge,
)
from testproject.testapp.models import HoldableOrder

from ..factories import CardHoldFactory, HoldableOrderFactory
from ..fakes import (
    STRIPE_CUSTOMER_ID,
    card_declined,
    connection_error,
    idempotency_error,
    unexpected_state,
)

CardHold = swapper.load_model("baseapp_payments", "CardHold")

pytestmark = pytest.mark.django_db


def live_hold(fake_stripe, *, status="requires_capture", **fields) -> Any:
    hold = CardHoldFactory(**fields)
    fake_stripe.intents[hold.stripe_payment_intent_id] = {
        "id": hold.stripe_payment_intent_id,
        "object": "payment_intent",
        "status": status,
        "amount": hold.amount_cents,
        "payment_method": "pm_visa",
        "capture_before": None,
        "amount_received": 0,
    }
    return hold


def expired_hold(fake_stripe, **fields) -> Any:
    """A hold past its capture deadline, its authorization still live in Stripe: any
    amount is charged afresh (released first), never captured from it, so these tests
    pin the charge path. An amount above a live hold is captured in full plus the
    difference instead (test_card_hold_above_hold)."""
    return live_hold(
        fake_stripe, expires_at=timezone.now() - datetime.timedelta(minutes=1), **fields
    )


def status_of(hold) -> str:
    hold.refresh_from_db()
    return hold.status


class TestCapturableHold:
    def test_an_authorized_unexpired_hold_covers_up_to_its_amount(self, order) -> None:
        hold = CardHoldFactory(target=order)

        assert capturable_hold(hold.pk, 11_000) == hold
        assert capturable_hold(hold.pk, 1) == hold
        assert capturable_hold(hold.pk, 11_001) is None
        assert capturable_hold(hold.pk, 0) is None

    @pytest.mark.parametrize(
        "fields",
        [
            {"status": "pending"},
            {"status": "released"},
            {"status": "captured"},
            {"expires_at": None},
        ],
    )
    def test_anything_else_is_not_capturable(self, order, fields) -> None:
        hold = CardHoldFactory(target=order, **fields)
        assert capturable_hold(hold.pk, 100) is None

    def test_an_expired_hold_is_not_capturable(self, order) -> None:
        hold = CardHoldFactory(
            target=order, expires_at=timezone.now() - datetime.timedelta(seconds=1)
        )
        assert capturable_hold(hold.pk, 100) is None


class TestCapture:
    def test_captures_exactly_the_amount_once(self, order, fake_stripe) -> None:
        hold = live_hold(fake_stripe, target=order)
        charge = Mock()

        result = capture(hold.pk, 10_500, charge=charge)

        assert result.status == CaptureStatus.CAPTURED
        assert fake_stripe.captures == [(hold.stripe_payment_intent_id, 10_500)]
        ((_args, params),) = fake_stripe.calls_to("PaymentIntent.capture")
        assert params["idempotency_key"] == f"testproject-capture-{hold.stripe_payment_intent_id}"
        assert status_of(hold) == CardHold.Status.CAPTURED
        assert hold.captured_amount_cents == 10_500
        assert hold.captured_at is not None
        charge.assert_not_called()

    def test_a_resumed_capture_replays_instead_of_charging_again(self, order, fake_stripe) -> None:
        """The first capture reached Stripe but its answer was lost before the row was
        written: the retry, with the same key, gets Stripe's replay."""
        hold = live_hold(fake_stripe, target=order)
        with patch("baseapp_payments.holds.mark_captured"):
            capture(hold.pk, 10_500, charge=Mock(), idempotency_key="k1")
        assert status_of(hold) == CardHold.Status.AUTHORIZED
        charge = Mock()

        result = capture(hold.pk, 10_500, charge=charge, idempotency_key="k1")

        assert result.status == CaptureStatus.CAPTURED
        assert len(fake_stripe.captures) == 1
        charge.assert_not_called()
        assert status_of(hold) == CardHold.Status.CAPTURED

    def test_capturing_twice_never_charges(self, order, fake_stripe) -> None:
        hold = live_hold(fake_stripe, target=order)
        capture(hold.pk, 10_500, charge=Mock())
        charge = Mock()

        # The caller retries (the same amount, or a corrected one above the hold).
        again = capture(hold.pk, 10_500, charge=charge)
        above = capture(hold.pk, 20_000, charge=charge)

        assert again.status == CaptureStatus.CAPTURED
        # Captured for 10,500: a retry asking 20,000 took nothing, so it doesn't say captured.
        assert above.status == CaptureStatus.NOT_CAPTURED
        # Answered from the recorded amount (#7): Stripe isn't read again.
        assert above.payment_intent is None and again.payment_intent is None
        assert fake_stripe.calls_to("PaymentIntent.retrieve") == []
        charge.assert_not_called()
        assert len(fake_stripe.calls_to("PaymentIntent.capture")) == 1
        assert fake_stripe.calls_to("PaymentIntent.cancel") == []

    def test_an_expired_hold_releases_then_charges_once(self, order, fake_stripe) -> None:
        hold = expired_hold(fake_stripe, target=order)
        events = []
        charge = Mock(
            side_effect=lambda **_kwargs: events.append(
                fake_stripe.status_of(hold.stripe_payment_intent_id)
            )
        )

        result = capture(hold.pk, 11_001, charge=charge)

        assert result.status == CaptureStatus.CHARGED
        charge.assert_called_once_with(idempotency_key=charge_idempotency_key(hold.pk))
        # Released before the charge ran: never a capture and a charge.
        assert events == ["canceled"]
        assert fake_stripe.calls_to("PaymentIntent.capture") == []
        assert status_of(hold) == CardHold.Status.RELEASED

    def test_a_decline_at_capture_is_never_followed_by_a_charge(self, order, fake_stripe) -> None:
        hold = live_hold(fake_stripe, target=order)
        fake_stripe.fail_next("PaymentIntent.capture", card_declined())
        charge = Mock()

        result = capture(hold.pk, 10_000, charge=charge)

        assert result.status == CaptureStatus.DECLINED
        charge.assert_not_called()
        assert status_of(hold) == CardHold.Status.RELEASED

    def test_a_decline_whose_release_fails_is_logged(self, order, fake_stripe, caplog) -> None:
        hold = live_hold(fake_stripe, target=order)
        fake_stripe.fail_next("PaymentIntent.capture", card_declined())
        fake_stripe.fail_next("PaymentIntent.cancel", connection_error())

        result = capture(hold.pk, 10_000, charge=Mock())

        assert result.status == CaptureStatus.DECLINED
        assert "Couldn't release declined card hold" in caplog.text

    def test_a_lapsed_authorization_is_charged_instead(self, order, fake_stripe) -> None:
        hold = live_hold(fake_stripe, target=order)
        fake_stripe.lapse(hold.stripe_payment_intent_id, canceled=False)
        charge = Mock(return_value="ch_new")

        result = capture(hold.pk, 10_000, charge=charge)

        assert result.status == CaptureStatus.CHARGED
        assert result.charge == "ch_new"
        charge.assert_called_once_with(idempotency_key=charge_idempotency_key(hold.pk))
        hold.refresh_from_db()
        assert hold.status == CardHold.Status.RELEASED
        assert hold.release_reason == CardHold.ReleaseReason.FOR_CHARGE
        assert hold.charged_at is not None

    def test_an_authorization_cancelled_elsewhere_is_never_charged(
        self, order, fake_stripe
    ) -> None:
        """M3: cancelled in Stripe outside this call (a release for a charge made
        elsewhere): charging on top could take the money twice."""
        hold = live_hold(fake_stripe, target=order)
        fake_stripe.set_status(hold.stripe_payment_intent_id, "canceled")
        charge = Mock(return_value="ch_new")

        result = capture(hold.pk, 10_000, charge=charge)

        assert result.status == CaptureStatus.NOT_CAPTURED
        charge.assert_not_called()
        hold.refresh_from_db()
        assert hold.status == CardHold.Status.RELEASED
        assert hold.release_reason == CardHold.ReleaseReason.LAPSED
        assert hold.release_confirmed_at is not None

    def test_a_hold_released_for_charge_is_not_charged_by_capture(self, order, fake_stripe) -> None:
        """release_for_charge hands the charge to its caller: a later capture() must not
        charge too."""
        hold = live_hold(fake_stripe, target=order)
        assert release_for_charge(hold.pk) is True
        charge = Mock()

        result = capture(hold.pk, 20_000, charge=charge)

        assert result.status == CaptureStatus.NOT_CAPTURED
        charge.assert_not_called()

    def test_a_double_capture_on_the_charge_path_charges_once(self, order, fake_stripe) -> None:
        """C1: the second call answers from the database."""
        hold = expired_hold(fake_stripe, target=order)
        charge = Mock(return_value="ch_new")

        first = capture(hold.pk, 20_000, charge=charge)
        second = capture(hold.pk, 20_000, charge=charge)

        assert first.status == second.status == CaptureStatus.CHARGED
        assert first.charge == "ch_new"
        assert second.charge is None
        charge.assert_called_once_with(idempotency_key=charge_idempotency_key(hold.pk))
        hold.refresh_from_db()
        assert hold.charge_key == charge_idempotency_key(hold.pk)
        assert hold.charged_at is not None
        assert hold.capture_claimed_at is None

    @pytest.mark.parametrize(
        "reason, confirmed",
        [
            ("", False),
            ("cancelled", True),
            ("card_released", True),
            ("abandoned", True),
            ("lapsed", True),
            ("declined", True),
            ("for_charge", True),
        ],
    )
    def test_a_hold_released_outside_capture_is_never_charged(
        self, order, fake_stripe, reason, confirmed
    ) -> None:
        """C1: only an allow-list of states is charged. A hold released by anything but
        this capture (its target cancelled, release_for_charge, a decline, Stripe) may
        have been charged elsewhere, so neither this call nor a retry charges it."""
        hold = live_hold(fake_stripe, target=order)
        CardHold.objects.filter(pk=hold.pk).update(
            status=CardHold.Status.RELEASED,
            release_reason=reason,
            release_confirmed_at=timezone.now() if confirmed else None,
        )
        charge = Mock(return_value="ch_new")

        first = capture(hold.pk, 10_000, charge=charge)
        again = capture(hold.pk, 10_000, charge=charge)

        assert first.status == again.status == CaptureStatus.NOT_CAPTURED
        charge.assert_not_called()
        assert fake_stripe.calls == []
        hold.refresh_from_db()
        assert hold.charge_key == "" and hold.charged_at is None

    def test_a_charge_that_raised_is_retried_with_the_same_key(self, order, fake_stripe) -> None:
        hold = expired_hold(fake_stripe, target=order)
        charge = Mock(side_effect=[stripe.APIConnectionError("lost"), "ch_new"])

        with pytest.raises(stripe.APIConnectionError):
            capture(hold.pk, 20_000, charge=charge)
        result = capture(hold.pk, 20_000, charge=charge)

        assert result.status == CaptureStatus.CHARGED
        assert result.charge == "ch_new"
        keys = [call.kwargs["idempotency_key"] for call in charge.call_args_list]
        assert keys == [charge_idempotency_key(hold.pk)] * 2
        # Released once; the retry didn't touch Stripe again.
        assert len(fake_stripe.calls_to("PaymentIntent.cancel")) == 1
        hold.refresh_from_db()
        assert hold.charged_at is not None and hold.capture_claimed_at is None

    def test_a_claimed_hold_answers_in_progress(self, order, fake_stripe) -> None:
        hold = live_hold(fake_stripe, target=order)
        CardHold.objects.filter(pk=hold.pk).update(capture_claimed_at=timezone.now())
        charge = Mock()

        result = capture(hold.pk, 10_000, charge=charge)

        assert result.status == CaptureStatus.IN_PROGRESS
        charge.assert_not_called()
        assert fake_stripe.calls == []

    def test_a_stale_claim_is_taken_over(self, order, fake_stripe) -> None:
        hold = live_hold(fake_stripe, target=order)
        CardHold.objects.filter(pk=hold.pk).update(
            capture_claimed_at=timezone.now() - datetime.timedelta(hours=1)
        )

        assert capture(hold.pk, 10_000, charge=Mock()).status == CaptureStatus.CAPTURED

    def test_a_missing_hold_charges_nothing(self, fake_stripe, caplog) -> None:
        """M5: no row, no claim and no record of the charge: charging blind could charge
        a target twice."""
        charge = Mock(return_value="ch_new")

        result = capture(987_654, 10_000, charge=charge)

        assert result.status == CaptureStatus.NOT_CAPTURED
        charge.assert_not_called()
        assert "no such hold" in caplog.text

    def test_a_reused_capture_key_is_not_captured(self, order, fake_stripe) -> None:
        """N4: an IdempotencyError maps to not_captured instead of propagating."""
        hold = live_hold(fake_stripe, target=order)
        fake_stripe.fail_next("PaymentIntent.capture", idempotency_error())
        charge = Mock()

        result = capture(hold.pk, 10_000, charge=charge)

        assert result.status == CaptureStatus.NOT_CAPTURED
        assert isinstance(result.error, stripe.IdempotencyError)
        charge.assert_not_called()
        assert status_of(hold) == CardHold.Status.AUTHORIZED

    def test_a_retry_with_another_amount_and_the_same_key_is_not_captured(
        self, order, fake_stripe
    ) -> None:
        hold = live_hold(fake_stripe, target=order)
        with patch("baseapp_payments.holds.mark_captured"):
            capture(hold.pk, 10_500, charge=Mock(), idempotency_key="k1")

        result = capture(hold.pk, 9_000, charge=Mock(), idempotency_key="k1")

        assert result.status == CaptureStatus.NOT_CAPTURED
        assert isinstance(result.error, stripe.IdempotencyError)

    def test_capturing_inside_atomic_raises(self, order, fake_stripe, settings) -> None:
        from django.db import transaction

        from baseapp_payments.holds import CardHoldInTransaction

        settings.BASEAPP_PAYMENTS_CARD_HOLD_REQUIRE_AUTOCOMMIT = True
        hold = live_hold(fake_stripe, target=order)

        with transaction.atomic(), pytest.raises(CardHoldInTransaction):
            capture(hold.pk, 10_000, charge=Mock())
        assert fake_stripe.calls == []

    def test_an_earlier_capture_of_this_attempt_is_recorded(self, order, fake_stripe) -> None:
        hold = live_hold(fake_stripe, target=order, status="succeeded")
        charge = Mock()

        result = capture(hold.pk, 10_000, charge=charge)

        assert result.status == CaptureStatus.CAPTURED
        charge.assert_not_called()
        assert status_of(hold) == CardHold.Status.CAPTURED

    def test_another_refusal_propagates(self, order, fake_stripe) -> None:
        hold = live_hold(fake_stripe, target=order)
        fake_stripe.fail_next(
            "PaymentIntent.capture",
            unexpected_state(hold.stripe_payment_intent_id, "processing", "capture"),
        )

        with pytest.raises(Exception):
            capture(hold.pk, 10_000, charge=Mock())

    def test_a_capture_that_doesnt_succeed_is_reported(self, order, fake_stripe) -> None:
        hold = live_hold(fake_stripe, target=order)
        fake_stripe.PaymentIntent.capture = Mock(
            return_value=stripe.PaymentIntent.construct_from(
                {"id": hold.stripe_payment_intent_id, "status": "processing"}, "sk"
            )
        )
        charge = Mock()

        result = capture(hold.pk, 10_000, charge=charge)

        assert result.status == CaptureStatus.NOT_CAPTURED
        charge.assert_not_called()
        assert status_of(hold) == CardHold.Status.AUTHORIZED

    def test_a_refused_release_charges_nothing(self, order, fake_stripe) -> None:
        hold = expired_hold(fake_stripe, target=order)
        refusal = unexpected_state(hold.stripe_payment_intent_id, "processing", "cancel")
        fake_stripe.fail_next("PaymentIntent.cancel", refusal)
        charge = Mock()

        result = capture(hold.pk, 20_000, charge=charge)

        assert result.status == CaptureStatus.NOT_CAPTURED
        assert result.error is refusal
        charge.assert_not_called()
        assert status_of(hold) == CardHold.Status.AUTHORIZED

    def test_a_transient_release_error_propagates_before_any_charge(
        self, order, fake_stripe
    ) -> None:
        hold = expired_hold(fake_stripe, target=order)
        fake_stripe.fail_next("PaymentIntent.cancel", connection_error())
        charge = Mock()

        with pytest.raises(stripe.APIConnectionError):
            capture(hold.pk, 20_000, charge=charge)

        charge.assert_not_called()

    def test_a_payment_intent_found_captured_at_release_is_recorded_not_charged(
        self, order, fake_stripe
    ) -> None:
        hold = live_hold(fake_stripe, target=order, status="succeeded")
        fake_stripe.intents[hold.stripe_payment_intent_id]["amount_received"] = 9_000
        charge = Mock()

        result = capture(hold.pk, 20_000, charge=charge)

        # Captured earlier for 9,000, not the 20,000 asked: nothing taken by this call.
        assert result.status == CaptureStatus.NOT_CAPTURED
        assert result.payment_intent["amount_received"] == 9_000
        charge.assert_not_called()
        hold.refresh_from_db()
        assert hold.status == CardHold.Status.CAPTURED
        assert hold.captured_amount_cents == 9_000

    def test_an_expired_hold_is_read_from_stripe_before_charging(self, order, fake_stripe) -> None:
        """M2: an expired hold Stripe still holds is cancelled before anything is
        charged; one Stripe cancelled itself is only confirmed; a captured one is
        recorded."""
        expired = timezone.now() - datetime.timedelta(minutes=1)
        captured = live_hold(fake_stripe, target=order, status="succeeded", expires_at=expired)
        still_held = live_hold(
            fake_stripe, target=HoldableOrderFactory(user=order.user), expires_at=expired
        )
        lapsed = live_hold(
            fake_stripe, target=HoldableOrderFactory(user=order.user), expires_at=expired
        )
        fake_stripe.lapse(lapsed.stripe_payment_intent_id)
        seen = []
        charge = Mock(side_effect=lambda **_kwargs: seen.append(dict(fake_stripe.intents)))

        assert capture(captured.pk, 10_000, charge=charge).status == CaptureStatus.CAPTURED
        charge.assert_not_called()
        assert status_of(captured) == CardHold.Status.CAPTURED

        assert capture(still_held.pk, 10_000, charge=charge).status == CaptureStatus.CHARGED
        assert seen[0][still_held.stripe_payment_intent_id]["status"] == "canceled"
        assert capture(lapsed.pk, 10_000, charge=charge).status == CaptureStatus.CHARGED
        assert charge.call_count == 2
        for hold in (still_held, lapsed):
            hold.refresh_from_db()
            assert hold.status == CardHold.Status.RELEASED
            assert hold.release_confirmed_at is not None
        cancelled = [args[0] for args, _kw in fake_stripe.calls_to("PaymentIntent.cancel")]
        assert still_held.stripe_payment_intent_id in cancelled

    def test_a_hold_released_to_be_rescheduled_charges_without_stripe(
        self, order, fake_stripe
    ) -> None:
        """Released ``rescheduled`` with its cancel confirmed: nothing of ours is held and
        nobody else charged, so it closes like a hold never placed, once."""
        hold = live_hold(fake_stripe, target=order)
        CardHold.objects.filter(pk=hold.pk).update(
            status=CardHold.Status.RELEASED,
            release_reason=CardHold.ReleaseReason.RESCHEDULED,
            release_confirmed_at=timezone.now(),
        )
        charge = Mock(return_value="ch_new")

        result = capture(hold.pk, 10_000, charge=charge)
        again = capture(hold.pk, 10_000, charge=charge)

        assert result.status == again.status == CaptureStatus.CHARGED
        charge.assert_called_once_with(idempotency_key=charge_idempotency_key(hold.pk))
        assert fake_stripe.calls == []
        hold.refresh_from_db()
        assert hold.release_reason == CardHold.ReleaseReason.FOR_CHARGE

    def test_a_reschedule_whose_cancel_isnt_confirmed_is_in_progress(
        self, order, fake_stripe
    ) -> None:
        hold = live_hold(fake_stripe, target=order)
        CardHold.objects.filter(pk=hold.pk).update(
            status=CardHold.Status.RELEASED, release_reason=CardHold.ReleaseReason.RESCHEDULED
        )
        charge = Mock()

        assert capture(hold.pk, 10_000, charge=charge).status == CaptureStatus.IN_PROGRESS
        charge.assert_not_called()

    def test_a_re_armed_hold_captures_with_its_own_key(
        self, order, fake_stripe, django_capture_on_commit_callbacks
    ) -> None:
        """A capture declined on the first authorization, then a re-arm and a capture of
        the new one: one key per authorization, so Stripe doesn't see a reused key."""
        hold = live_hold(fake_stripe, target=order)
        old_payment_intent_id = hold.stripe_payment_intent_id
        fake_stripe.fail_next("PaymentIntent.capture", card_declined())
        assert capture(hold.pk, 10_000, charge=Mock()).status == CaptureStatus.DECLINED

        with django_capture_on_commit_callbacks(execute=True):
            rearmed = authorize_on_session(
                user=order.user,
                attempt_id=uuid.uuid4(),
                payment_method_id="pm_visa",
                stripe_customer_id=STRIPE_CUSTOMER_ID,
                target=order,
                expected_amount_cents=10_000,
            )
        assert rearmed.status == PlacementStatus.PLACED
        hold.refresh_from_db()
        assert hold.stripe_payment_intent_id != old_payment_intent_id

        result = capture(hold.pk, 10_000, charge=Mock())

        assert result.status == CaptureStatus.CAPTURED
        keys = [
            params["idempotency_key"]
            for _a, params in fake_stripe.calls_to("PaymentIntent.capture")
        ]
        assert keys == [
            f"testproject-capture-{old_payment_intent_id}",
            f"testproject-capture-{hold.stripe_payment_intent_id}",
        ]

    def test_the_fake_refuses_a_capture_key_reused_for_another_payment_intent(
        self, order, fake_stripe
    ) -> None:
        first = live_hold(fake_stripe, target=order)
        second = live_hold(fake_stripe, target=HoldableOrderFactory(user=order.user))
        fake_stripe.PaymentIntent.capture(first.stripe_payment_intent_id, idempotency_key="same")

        with pytest.raises(stripe.IdempotencyError):
            fake_stripe.PaymentIntent.capture(
                second.stripe_payment_intent_id, idempotency_key="same"
            )

    def test_mark_captured_is_idempotent(self, order) -> None:
        hold = CardHoldFactory(target=order)
        assert mark_captured(hold.pk) is True
        assert mark_captured(hold.pk) is False


class TestCaptureEdges:
    def test_a_captured_hold_answers_from_its_recorded_amount(self, order, fake_stripe) -> None:
        """#7: no Stripe call when the amount captured is recorded."""
        hold = live_hold(fake_stripe, target=order)
        mark_captured(hold.pk, amount_cents=9_000)
        charge = Mock()

        assert capture(hold.pk, 9_000, charge=charge).status == CaptureStatus.CAPTURED
        assert capture(hold.pk, 9_500, charge=charge).status == CaptureStatus.NOT_CAPTURED
        assert fake_stripe.calls == []
        charge.assert_not_called()

    def test_a_captured_hold_with_no_recorded_amount_reads_stripe(self, order, fake_stripe) -> None:
        hold = live_hold(fake_stripe, target=order, status="succeeded")
        fake_stripe.intents[hold.stripe_payment_intent_id]["amount_received"] = 9_000
        mark_captured(hold.pk, amount_cents=None)

        assert capture(hold.pk, 9_000, charge=Mock()).status == CaptureStatus.CAPTURED
        assert len(fake_stripe.calls_to("PaymentIntent.retrieve")) == 1

    def test_a_negative_amount_raises(self, order, fake_stripe) -> None:
        hold = live_hold(fake_stripe, target=order)
        charge = Mock()

        with pytest.raises(ValueError):
            capture(hold.pk, -1, charge=charge)
        assert fake_stripe.calls == []
        assert CardHold.objects.get(pk=hold.pk).capture_claimed_at is None

    def test_zero_releases_an_open_hold_and_charges_nothing(self, order, fake_stripe) -> None:
        """#8: a capture of 0 charged afresh."""
        hold = live_hold(fake_stripe, target=order)
        charge = Mock()

        assert capture(hold.pk, 0, charge=charge).status == CaptureStatus.NOTHING_DUE
        assert capture(hold.pk, 0, charge=charge).status == CaptureStatus.NOTHING_DUE
        charge.assert_not_called()
        hold.refresh_from_db()
        assert hold.status == CardHold.Status.RELEASED
        assert hold.release_reason == CardHold.ReleaseReason.CARD_RELEASED
        assert hold.release_confirmed_at is not None and hold.charge_key == ""
        assert fake_stripe.status_of(hold.stripe_payment_intent_id) == "canceled"
        assert capture(hold.pk, 10_000, charge=charge).status == CaptureStatus.NOT_CAPTURED
        charge.assert_not_called()

    @pytest.mark.parametrize("status", ["scheduled", "saved"])
    def test_zero_releases_an_unplaced_hold_with_no_stripe_call(
        self, order, fake_stripe, status
    ) -> None:
        hold = CardHoldFactory(target=order, status=status, stripe_payment_intent_id=None)
        charge = Mock()

        assert capture(hold.pk, 0, charge=charge).status == CaptureStatus.NOTHING_DUE
        assert status_of(hold) == CardHold.Status.RELEASED
        assert fake_stripe.calls == []
        charge.assert_not_called()

    def test_zero_waits_for_a_placement_under_way(self, order, fake_stripe) -> None:
        hold = CardHoldFactory(
            target=order,
            status=CardHold.Status.SCHEDULED,
            stripe_payment_intent_id=None,
            placement_key="k",
        )

        assert capture(hold.pk, 0, charge=Mock()).status == CaptureStatus.IN_PROGRESS
        assert status_of(hold) == CardHold.Status.SCHEDULED

    def test_zero_on_failed_holds(self, order, fake_stripe) -> None:
        undecided = CardHoldFactory(
            target=order, status=CardHold.Status.FAILED, stripe_payment_intent_id=None
        )
        kept = CardHoldFactory(
            target=HoldableOrderFactory(user=order.user),
            status=CardHold.Status.FAILED,
            stripe_payment_intent_id=None,
            kept_at=timezone.now(),
        )
        charge = Mock()

        assert capture(undecided.pk, 0, charge=charge).status == CaptureStatus.NOT_CAPTURED
        assert capture(kept.pk, 0, charge=charge).status == CaptureStatus.NOTHING_DUE
        assert status_of(undecided) == CardHold.Status.FAILED
        assert status_of(kept) == CardHold.Status.RELEASED
        CardHold.objects.filter(pk=undecided.pk).update(kept_at=timezone.now(), charge_key="x")
        undecided.refresh_from_db()
        from baseapp_payments import holds

        assert holds._nothing_due(undecided).status == CaptureStatus.IN_PROGRESS
        charge.assert_not_called()

    @pytest.mark.parametrize("reason", ["rescheduled", "not_holdable"])
    def test_zero_on_a_hold_going_back_to_scheduled(self, order, fake_stripe, reason) -> None:
        hold = live_hold(fake_stripe, target=order)
        CardHold.objects.filter(pk=hold.pk).update(
            status=CardHold.Status.RELEASED, release_reason=reason
        )
        charge = Mock()

        assert capture(hold.pk, 0, charge=charge).status == CaptureStatus.IN_PROGRESS
        CardHold.objects.filter(pk=hold.pk).update(release_confirmed_at=timezone.now())
        assert capture(hold.pk, 0, charge=charge).status == CaptureStatus.NOTHING_DUE
        hold.refresh_from_db()
        assert hold.release_reason == CardHold.ReleaseReason.CARD_RELEASED
        charge.assert_not_called()

    def test_zero_on_an_authorization_found_captured_or_cancelled_elsewhere(
        self, order, fake_stripe
    ) -> None:
        captured = live_hold(fake_stripe, target=order, status="succeeded")
        fake_stripe.intents[captured.stripe_payment_intent_id]["amount_received"] = 5_000
        elsewhere = live_hold(
            fake_stripe, target=HoldableOrderFactory(user=order.user), status="canceled"
        )
        charge = Mock()

        assert capture(captured.pk, 0, charge=charge).status == CaptureStatus.NOT_CAPTURED
        assert status_of(captured) == CardHold.Status.CAPTURED
        assert capture(elsewhere.pk, 0, charge=charge).status == CaptureStatus.NOT_CAPTURED
        charge.assert_not_called()


class TestZeroIsPaid:
    """A capture of 0 owes nothing: once the hold is released, the target is ``paid``."""

    @pytest.fixture
    def heard(self) -> Any:
        from baseapp_payments.signals import payment_status_changed

        changes: list[tuple[str, str]] = []

        def on_status(sender: Any, **kwargs: Any) -> None:
            changes.append((kwargs["previous"], kwargs["payment_status"]))

        payment_status_changed.connect(on_status, weak=False)
        try:
            with patch(
                "baseapp_payments.holds.send_on_commit",
                side_effect=lambda signal, **kwargs: signal.send_robust(sender=CardHold, **kwargs),
            ):
                yield changes
        finally:
            payment_status_changed.disconnect(on_status)

    def test_an_open_hold_released_is_paid_once(self, order, fake_stripe, heard) -> None:
        hold = live_hold(fake_stripe, target=order)

        assert capture(hold.pk, 0, charge=Mock()).status == CaptureStatus.NOTHING_DUE
        assert capture(hold.pk, 0, charge=Mock()).status == CaptureStatus.NOTHING_DUE

        hold.refresh_from_db()
        assert hold.payment_status == CardHold.PaymentStatus.PAID
        assert heard == [("unpaid", "paid")]

    def test_an_unplaced_hold_released_is_paid(self, order, fake_stripe, heard) -> None:
        hold = CardHoldFactory(target=order, status="scheduled", stripe_payment_intent_id=None)

        assert capture(hold.pk, 0, charge=Mock()).status == CaptureStatus.NOTHING_DUE

        hold.refresh_from_db()
        assert hold.payment_status == CardHold.PaymentStatus.PAID
        assert heard == [("unpaid", "paid")]

    def test_the_signal_waits_for_the_commit(self, order, fake_stripe) -> None:
        hold = live_hold(fake_stripe, target=order)

        with patch("baseapp_payments.holds.send_on_commit") as on_commit:
            capture(hold.pk, 0, charge=Mock())

        sent = [
            kwargs["payment_status"]
            for _args, kwargs in on_commit.call_args_list
            if "payment_status" in kwargs
        ]
        assert sent == [CardHold.PaymentStatus.PAID]

    def test_not_while_the_release_is_under_way(self, order, fake_stripe, heard) -> None:
        placing = CardHoldFactory(
            target=order, status="scheduled", stripe_payment_intent_id=None, placement_key="k"
        )
        unconfirmed = live_hold(fake_stripe, target=HoldableOrderFactory(user=order.user))
        CardHold.objects.filter(pk=unconfirmed.pk).update(
            status=CardHold.Status.RELEASED, release_reason="rescheduled"
        )

        assert capture(placing.pk, 0, charge=Mock()).status == CaptureStatus.IN_PROGRESS
        assert capture(unconfirmed.pk, 0, charge=Mock()).status == CaptureStatus.IN_PROGRESS

        for hold in (placing, unconfirmed):
            hold.refresh_from_db()
            assert hold.payment_status == CardHold.PaymentStatus.UNPAID
        assert heard == []

    def test_never_for_a_charge_that_never_finished(self, order, fake_stripe, heard) -> None:
        hold = CardHoldFactory(
            target=order,
            status=CardHold.Status.RELEASED,
            stripe_payment_intent_id=None,
            charge_key="k",
            charge_claimed_at=timezone.now(),
        )

        assert capture(hold.pk, 0, charge=Mock()).status == CaptureStatus.IN_PROGRESS

        hold.refresh_from_db()
        assert hold.payment_status == CardHold.PaymentStatus.UNPAID
        assert heard == []

    def test_not_when_nothing_was_released(self, order, fake_stripe, heard) -> None:
        elsewhere = live_hold(fake_stripe, target=order, status="canceled")

        assert capture(elsewhere.pk, 0, charge=Mock()).status == CaptureStatus.NOT_CAPTURED

        elsewhere.refresh_from_db()
        assert elsewhere.payment_status == CardHold.PaymentStatus.UNPAID
        assert heard == []


class TestCardInUse:
    def test_a_hold_on_an_active_target_is_in_use_whatever_its_status(self, holder) -> None:
        for status in ("authorized", "released", "pending"):
            CardHoldFactory(
                target=HoldableOrderFactory(user=holder),
                status=status,
                stripe_payment_method_id=f"pm_{status}",
            )

        assert in_use_payment_method_ids(holder) == {"pm_authorized", "pm_released", "pm_pending"}

    def test_cancelled_and_card_released_targets_free_the_card(self, holder) -> None:
        CardHoldFactory(
            target=HoldableOrderFactory(user=holder, status=HoldableOrder.Status.CANCELLED),
            stripe_payment_method_id="pm_a",
        )
        CardHoldFactory(
            target=HoldableOrderFactory(user=holder, status=HoldableOrder.Status.CHARGED),
            stripe_payment_method_id="pm_b",
        )

        assert in_use_payment_method_ids(holder) == set()
        assert not card_in_use(holder, "pm_a")

    def test_an_unlinked_pending_hold_is_in_use_whatever_its_age(self, holder) -> None:
        old = CardHoldFactory(customer=holder, status="pending", stripe_payment_method_id="pm_p")
        CardHold.objects.filter(pk=old.pk).update(
            created=timezone.now() - datetime.timedelta(days=3)
        )
        CardHoldFactory(customer=holder, status="released", stripe_payment_method_id="pm_r")

        assert card_in_use(holder, "pm_p")
        assert not card_in_use(holder, "pm_r")

    def test_other_customers_holds_dont_count(self, holder) -> None:
        CardHoldFactory(target=HoldableOrderFactory(), stripe_payment_method_id="pm_visa")

        assert not card_in_use(holder, "pm_visa")

    def test_is_one_query(self, holder, django_assert_num_queries) -> None:
        CardHoldFactory(target=HoldableOrderFactory(user=holder), attempt_id=uuid.uuid4())

        with django_assert_num_queries(1):
            in_use_payment_method_ids(holder)
