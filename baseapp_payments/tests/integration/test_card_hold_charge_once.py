"""A retry of capture() never charges what an earlier call refused to (C1), and a
charge is never re-run once Stripe may have forgotten its key (M5)."""

import datetime
import uuid
from typing import Any
from unittest.mock import Mock, patch

import pytest
import stripe
import swapper
from django.utils import timezone

from baseapp_payments import holds
from baseapp_payments.holds import (
    CHARGE_KEY_TTL,
    CaptureStatus,
    PlacementStatus,
    authorize_on_session,
    capture,
    charge_idempotency_key,
    release_for_charge,
)
from baseapp_payments.tasks import sweep_card_holds
from testproject.testapp.models import HoldableOrder

from ..factories import CardHoldFactory, HoldableOrderFactory
from ..fakes import (
    STRIPE_CUSTOMER_ID,
    card_declined,
    connection_error,
    idempotency_error,
    project_charge,
)

CardHold = swapper.load_model("baseapp_payments", "CardHold")

pytestmark = pytest.mark.django_db


def live_hold(fake_stripe, **fields) -> Any:
    hold = CardHoldFactory(**fields)
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


def expired_hold(fake_stripe, **fields) -> Any:
    """A hold past its capture deadline, its authorization still live in Stripe: any
    amount is charged afresh (released first), never captured from it, so these tests
    pin the charge path. An amount above a live hold is captured in full plus the
    difference instead (test_card_hold_above_hold)."""
    return live_hold(
        fake_stripe, expires_at=timezone.now() - datetime.timedelta(minutes=1), **fields
    )


def reload(hold) -> Any:
    hold.refresh_from_db()
    return hold


class TestRetriesNeverUndoARefusal:
    def test_a_retry_after_a_cancel_elsewhere_charges_nothing(self, order, fake_stripe) -> None:
        """Reviewer's repro: the first call answered not_captured, the retry charged."""
        hold = live_hold(fake_stripe, target=order)
        fake_stripe.set_status(hold.stripe_payment_intent_id, "canceled")
        charge = Mock(return_value="ch")

        first = capture(hold.pk, 10_000, charge=charge)
        second = capture(hold.pk, 10_000, charge=charge)
        above = capture(hold.pk, 20_000, charge=charge)

        assert first.status == second.status == above.status == CaptureStatus.NOT_CAPTURED
        charge.assert_not_called()
        hold = reload(hold)
        assert hold.release_reason == CardHold.ReleaseReason.LAPSED
        assert hold.charge_blocked_reason == CardHold.ChargeBlock.LAPSED

    def test_a_retry_after_a_decline_charges_nothing(self, order, fake_stripe) -> None:
        """Reviewer's repro: declined, then the retry charged."""
        hold = live_hold(fake_stripe, target=order)
        fake_stripe.fail_next("PaymentIntent.capture", card_declined())
        charge = Mock(return_value="ch")

        assert capture(hold.pk, 10_000, charge=charge).status == CaptureStatus.DECLINED
        second = capture(hold.pk, 10_000, charge=charge)
        above = capture(hold.pk, 20_000, charge=charge)

        assert second.status == above.status == CaptureStatus.NOT_CAPTURED
        charge.assert_not_called()
        assert reload(hold).charge_blocked_reason == CardHold.ChargeBlock.DECLINED

    def test_a_decline_whose_release_failed_isnt_charged_once_the_hold_expires(
        self, order, fake_stripe
    ) -> None:
        """The release after a decline didn't go through, so the hold reads authorized;
        once it expires a retry would have charged instead. The marker stops it."""
        hold = live_hold(fake_stripe, target=order)
        fake_stripe.fail_next("PaymentIntent.capture", card_declined())
        fake_stripe.fail_next("PaymentIntent.cancel", connection_error())
        charge = Mock(return_value="ch")
        assert capture(hold.pk, 10_000, charge=charge).status == CaptureStatus.DECLINED
        assert reload(hold).status == CardHold.Status.AUTHORIZED
        CardHold.objects.filter(pk=hold.pk).update(
            expires_at=timezone.now() - datetime.timedelta(minutes=1)
        )

        assert capture(hold.pk, 20_000, charge=charge).status == CaptureStatus.NOT_CAPTURED
        charge.assert_not_called()
        assert fake_stripe.calls_to("PaymentIntent.cancel")[1:] == []

    @pytest.mark.parametrize("reason", ["expired", "automatic"], ids=["basil", "acacia"])
    def test_an_authorization_stripe_cancelled_when_it_lapsed_is_charged_instead(
        self, order, fake_stripe, reason
    ) -> None:
        """``canceled`` with ``cancellation_reason: expired`` (``automatic`` before
        2025-03-31.basil): it expired by itself, nobody charged, so the amount is charged
        afresh (once)."""
        hold = live_hold(fake_stripe, target=order)
        fake_stripe.lapse(hold.stripe_payment_intent_id, reason=reason)
        charge = Mock(return_value="ch_new")

        result = capture(hold.pk, 10_000, charge=charge)
        again = capture(hold.pk, 10_000, charge=charge)

        assert result.status == again.status == CaptureStatus.CHARGED
        charge.assert_called_once_with(idempotency_key=charge_idempotency_key(hold.pk))
        hold = reload(hold)
        assert hold.release_reason == CardHold.ReleaseReason.FOR_CHARGE
        assert hold.charge_blocked_reason == ""

    def test_an_expired_hold_someone_else_cancelled_isnt_charged(self, order, fake_stripe) -> None:
        """The charge-instead path asks Stripe too: a PaymentIntent found cancelled by
        someone else (not Stripe's own expiry) may have been charged elsewhere."""
        hold = live_hold(
            fake_stripe,
            target=order,
            expires_at=timezone.now() - datetime.timedelta(minutes=1),
        )
        fake_stripe.set_status(hold.stripe_payment_intent_id, "canceled")
        charge = Mock()

        assert capture(hold.pk, 10_000, charge=charge).status == CaptureStatus.NOT_CAPTURED
        assert capture(hold.pk, 10_000, charge=charge).status == CaptureStatus.NOT_CAPTURED
        charge.assert_not_called()
        assert reload(hold).charge_blocked_reason == CardHold.ChargeBlock.LAPSED

    def test_a_release_by_another_call_meanwhile_isnt_charged(self, order, fake_stripe) -> None:
        """The UPDATE that releases the hold also claims the charge: when another call
        released the row between the read and the cancel, this one doesn't charge."""
        hold = expired_hold(fake_stripe, target=order)
        cancel = holds._cancel_payment_intent

        def released_meanwhile(payment_intent_id: str, card_hold_id: int) -> Any:
            CardHold.objects.filter(pk=card_hold_id).update(
                status=CardHold.Status.RELEASED,
                release_reason=CardHold.ReleaseReason.CANCELLED,
            )
            return cancel(payment_intent_id, card_hold_id)

        charge = Mock()
        with patch.object(holds, "_cancel_payment_intent", side_effect=released_meanwhile):
            result = capture(hold.pk, 20_000, charge=charge)

        assert result.status == CaptureStatus.NOT_CAPTURED
        charge.assert_not_called()
        assert reload(hold).charge_key == ""

    def test_a_failed_hold_not_kept_is_never_charged(self, order, fake_stripe) -> None:
        hold = CardHoldFactory(
            target=order, status=CardHold.Status.FAILED, stripe_payment_intent_id=None
        )
        charge = Mock()

        assert capture(hold.pk, 10_000, charge=charge).status == CaptureStatus.NOT_CAPTURED
        charge.assert_not_called()


class TestReleaseForChargeTakesTheClaim:
    def test_it_answers_false_while_a_capture_holds_the_claim(self, order, fake_stripe) -> None:
        """C1: release_for_charge took no claim, so it could cancel the authorization
        under a running capture and both callers charged."""
        hold = live_hold(fake_stripe, target=order)
        CardHold.objects.filter(pk=hold.pk).update(capture_claimed_at=timezone.now())

        assert release_for_charge(hold.pk) is False
        assert fake_stripe.calls == []
        assert reload(hold).status == CardHold.Status.AUTHORIZED

    def test_a_capture_answers_in_progress_while_it_runs(self, order, fake_stripe) -> None:
        hold = live_hold(fake_stripe, target=order)
        seen = []

        def cancel_and_capture(payment_intent_id: str, card_hold_id: int) -> Any:
            seen.append(capture(card_hold_id, 10_000, charge=Mock()).status)
            return (holds._Cancel.CANCELED, None)

        with patch.object(holds, "_cancel_payment_intent", side_effect=cancel_and_capture):
            assert release_for_charge(hold.pk) is True

        assert seen == [CaptureStatus.IN_PROGRESS]
        hold = reload(hold)
        assert hold.release_reason == CardHold.ReleaseReason.FOR_CHARGE
        assert hold.capture_claimed_at is None

    def test_it_never_answers_true_for_what_capture_settled(self, order, fake_stripe) -> None:
        """A capture that found the authorization cancelled elsewhere, one that charged
        instead, and one that captured: release_for_charge's caller must not charge."""
        elsewhere = live_hold(fake_stripe, target=order)
        fake_stripe.set_status(elsewhere.stripe_payment_intent_id, "canceled")
        capture(elsewhere.pk, 10_000, charge=Mock())
        charged = live_hold(fake_stripe, target=HoldableOrderFactory(user=order.user))
        capture(charged.pk, 20_000, charge=Mock())
        captured = live_hold(fake_stripe, target=HoldableOrderFactory(user=order.user))
        capture(captured.pk, 10_000, charge=Mock())

        assert release_for_charge(elsewhere.pk) is False
        assert release_for_charge(charged.pk) is False
        assert release_for_charge(captured.pk) is False

    def test_a_repeated_call_answers_true_again(self, order, fake_stripe) -> None:
        hold = live_hold(fake_stripe, target=order)

        assert release_for_charge(hold.pk) is True
        assert release_for_charge(hold.pk) is True
        assert len(fake_stripe.calls_to("PaymentIntent.cancel")) == 1

    def test_a_payment_intent_someone_else_cancelled_answers_false(
        self, order, fake_stripe
    ) -> None:
        hold = live_hold(fake_stripe, target=order)
        fake_stripe.set_status(hold.stripe_payment_intent_id, "canceled")

        assert release_for_charge(hold.pk) is False
        assert reload(hold).charge_blocked_reason == CardHold.ChargeBlock.LAPSED

    def test_a_missing_hold_answers_false(self, fake_stripe) -> None:
        assert release_for_charge(987_654) is False

    def test_it_raises_inside_a_transaction(self, order, fake_stripe, settings) -> None:
        from django.db import transaction

        from baseapp_payments.holds import CardHoldInTransaction

        settings.BASEAPP_PAYMENTS_CARD_HOLD_REQUIRE_AUTOCOMMIT = True
        hold = live_hold(fake_stripe, target=order)

        with transaction.atomic(), pytest.raises(CardHoldInTransaction):
            release_for_charge(hold.pk)
        assert fake_stripe.calls == []


class TestChargeKeyLifetime:
    def test_a_charge_retried_within_the_day_reuses_its_key(self, order, fake_stripe) -> None:
        hold = expired_hold(fake_stripe, target=order)
        charge = Mock(side_effect=[stripe.APIConnectionError("lost"), "ch_new"])
        with pytest.raises(stripe.APIConnectionError):
            capture(hold.pk, 20_000, charge=charge)
        CardHold.objects.filter(pk=hold.pk).update(
            charge_claimed_at=timezone.now() - CHARGE_KEY_TTL + datetime.timedelta(minutes=5)
        )

        assert capture(hold.pk, 20_000, charge=charge).status == CaptureStatus.CHARGED
        assert charge.call_count == 2

    def test_a_charge_older_than_stripe_keeps_its_key_is_not_re_run(
        self, order, fake_stripe, caplog
    ) -> None:
        """M5: Stripe forgets an idempotency key after 24 hours, so re-running the charge
        with it could charge twice. Blocked, logged, reconciled by hand."""
        hold = expired_hold(fake_stripe, target=order)
        charge = Mock(side_effect=[stripe.APIConnectionError("lost"), "ch_new"])
        with pytest.raises(stripe.APIConnectionError):
            capture(hold.pk, 20_000, charge=charge)
        CardHold.objects.filter(pk=hold.pk).update(
            charge_claimed_at=timezone.now() - CHARGE_KEY_TTL - datetime.timedelta(minutes=1)
        )

        with caplog.at_level("ERROR", logger="baseapp_payments.holds"):
            result = capture(hold.pk, 20_000, charge=charge)
        again = capture(hold.pk, 20_000, charge=charge)

        assert result.status == again.status == CaptureStatus.NOT_CAPTURED
        assert charge.call_count == 1
        assert "settle it by hand" in caplog.text
        assert reload(hold).charge_blocked_reason == CardHold.ChargeBlock.STALE_CHARGE

    def test_a_charge_key_of_unknown_age_is_not_re_run(self, order, fake_stripe) -> None:
        hold = live_hold(fake_stripe, target=order)
        CardHold.objects.filter(pk=hold.pk).update(
            status=CardHold.Status.RELEASED, charge_key=charge_idempotency_key(hold.pk)
        )
        charge = Mock()

        assert capture(hold.pk, 10_000, charge=charge).status == CaptureStatus.NOT_CAPTURED
        charge.assert_not_called()

    def test_a_finished_charge_answers_charged_whatever_its_age(self, order, fake_stripe) -> None:
        hold = live_hold(fake_stripe, target=order)
        CardHold.objects.filter(pk=hold.pk).update(
            status=CardHold.Status.RELEASED,
            charge_key=charge_idempotency_key(hold.pk),
            charge_claimed_at=timezone.now() - datetime.timedelta(days=30),
            charged_at=timezone.now() - datetime.timedelta(days=30),
        )
        charge = Mock()

        assert capture(hold.pk, 10_000, charge=charge).status == CaptureStatus.CHARGED
        charge.assert_not_called()

    def test_the_pending_row_a_re_arm_deletes_is_never_charged(self, order, fake_stripe) -> None:
        """M5: re-arming folds the new pending row into the target's hold and deletes it;
        a capture of that id finds no row and charges nothing."""
        CardHoldFactory(
            target=order,
            status=CardHold.Status.RELEASED,
            stripe_payment_intent_id="pi_old",
            release_confirmed_at=timezone.now(),
        )
        pending = []
        record = holds.record_pending_hold

        def recording(**kwargs: Any) -> Any:
            pending.append(record(**kwargs))
            return pending[-1]

        with patch.object(holds, "record_pending_hold", side_effect=recording):
            result = authorize_on_session(
                user=order.user,
                attempt_id=uuid.uuid4(),
                payment_method_id="pm_visa",
                stripe_customer_id=STRIPE_CUSTOMER_ID,
                target=order,
                expected_amount_cents=order.amount_cents,
            )
        assert result.status == PlacementStatus.PLACED
        (deleted,) = pending
        assert not CardHold.objects.filter(pk=deleted.pk).exists()
        charge = Mock()

        assert capture(deleted.pk, 10_000, charge=charge).status == CaptureStatus.NOT_CAPTURED
        charge.assert_not_called()


class TestTheChargeClaimIsConditional:
    """Each charge-instead state claims the charge in a conditional UPDATE; a row that
    changed since it was read claims nothing and charges nothing."""

    def test_a_lapse_released_meanwhile_isnt_charged(self, order, fake_stripe) -> None:
        hold = live_hold(fake_stripe, target=order)
        fake_stripe.lapse(hold.stripe_payment_intent_id, canceled=False)
        charge = Mock()

        with patch.object(holds, "mark_released", return_value=False):
            result = capture(hold.pk, 10_000, charge=charge)

        assert result.status == CaptureStatus.NOT_CAPTURED
        charge.assert_not_called()

    def test_a_reschedule_that_moved_on_isnt_charged(self, order, fake_stripe) -> None:
        hold = live_hold(fake_stripe, target=order)
        CardHold.objects.filter(pk=hold.pk).update(
            status=CardHold.Status.RELEASED,
            release_reason=CardHold.ReleaseReason.RESCHEDULED,
            release_confirmed_at=timezone.now(),
        )
        seen = reload(hold)
        # Back to scheduled by reschedule() since it was read.
        CardHold.objects.filter(pk=hold.pk).update(status=CardHold.Status.SCHEDULED)
        charge = Mock()

        assert holds._charge_released(seen, charge, 10_000).status == CaptureStatus.IN_PROGRESS
        charge.assert_not_called()

    def test_a_kept_failed_hold_changed_meanwhile_isnt_charged(self, order, fake_stripe) -> None:
        hold = CardHoldFactory(
            target=order,
            status=CardHold.Status.FAILED,
            stripe_payment_intent_id=None,
            kept_at=timezone.now(),
        )
        CardHold.objects.filter(pk=hold.pk).update(charge_key="someone-else")
        charge = Mock()

        assert holds._charge_instead(hold, 10_000, charge).status == CaptureStatus.NOT_CAPTURED
        charge.assert_not_called()


class TestARefusedChargeGetsANewKey:
    """#1: Stripe saves a decline for its key and replays it for 24 hours, and the same
    key with another card raises IdempotencyError. A definite refusal drops the claim
    and bumps the key's generation; only no answer keeps the key."""

    def test_a_decline_then_a_retry_with_a_new_card_charges_once_with_a_new_key(
        self, order, fake_stripe
    ) -> None:
        hold = expired_hold(fake_stripe, target=order)
        fake_stripe.next_outcome = ["card_declined"]

        first = capture(hold.pk, 20_000, charge=project_charge(fake_stripe, amount=20_000))
        hold = reload(hold)
        assert first.status == CaptureStatus.DECLINED
        assert isinstance(first.error, stripe.CardError)
        assert (hold.charge_key, hold.charge_claimed_at) == ("", None)
        assert hold.charge_generation == 1 and hold.charge_blocked_reason == ""
        assert release_for_charge(hold.pk) is False  # capture() owns this charge

        new_card = project_charge(fake_stripe, payment_method="pm_new", amount=20_000)
        retried = capture(hold.pk, 20_000, charge=new_card)
        again = capture(hold.pk, 20_000, charge=new_card)

        assert retried.status == again.status == CaptureStatus.CHARGED
        charges = fake_stripe.calls_to("PaymentIntent.create")
        assert [params["idempotency_key"] for _args, params in charges] == [
            charge_idempotency_key(hold.pk, 0),
            charge_idempotency_key(hold.pk, 1),
        ]
        assert charges[1][1]["payment_method"] == "pm_new"
        hold = reload(hold)
        assert hold.charged_at is not None
        assert hold.charge_key == charge_idempotency_key(hold.pk, 1)

    def test_an_invalid_request_is_definite_too(self, order, fake_stripe) -> None:
        hold = expired_hold(fake_stripe, target=order)
        refused = stripe.InvalidRequestError("No such PaymentMethod", None, http_status=400)
        charge = Mock(side_effect=[refused, "ch_new"])

        assert capture(hold.pk, 20_000, charge=charge).status == CaptureStatus.DECLINED
        assert capture(hold.pk, 20_000, charge=charge).status == CaptureStatus.CHARGED
        assert [call.kwargs["idempotency_key"] for call in charge.call_args_list] == [
            charge_idempotency_key(hold.pk, 0),
            charge_idempotency_key(hold.pk, 1),
        ]

    @pytest.mark.parametrize(
        "error",
        [
            connection_error(),
            stripe.APIError("Stripe had a problem.", http_status=500),
            stripe.RateLimitError("Too many requests", http_status=429),
            stripe.InvalidRequestError("In use", None, http_status=409),
            stripe.AuthenticationError("Invalid API key", http_status=401),
            stripe.PermissionError("Not allowed", http_status=403),
            idempotency_error(),
        ],
        ids=["connection", "5xx", "429", "409", "401", "403", "idempotency"],
    )
    def test_no_answer_keeps_the_claim_and_its_key(self, order, fake_stripe, error) -> None:
        hold = expired_hold(fake_stripe, target=order)
        charge = Mock(side_effect=[error, "ch_new"])

        with pytest.raises(type(error)):
            capture(hold.pk, 20_000, charge=charge)
        hold = reload(hold)
        assert hold.charge_key == charge_idempotency_key(hold.pk, 0)
        assert hold.charge_claimed_at is not None and hold.charge_generation == 0

        assert capture(hold.pk, 20_000, charge=charge).status == CaptureStatus.CHARGED
        assert [call.kwargs["idempotency_key"] for call in charge.call_args_list] == [
            charge_idempotency_key(hold.pk, 0)
        ] * 2

    def test_the_stale_ttl_only_applies_to_a_no_answer_claim(
        self, order, fake_stripe, caplog
    ) -> None:
        """A decline a day old is retried with a new key; a no-answer claim as old is
        blocked, with a message that says what happened."""
        declined = expired_hold(fake_stripe, target=order)
        charge = Mock(side_effect=[card_declined(), "ch_new"])
        assert capture(declined.pk, 20_000, charge=charge).status == CaptureStatus.DECLINED
        CardHold.objects.filter(pk=declined.pk).update(
            modified=timezone.now() - CHARGE_KEY_TTL - datetime.timedelta(hours=1)
        )
        assert capture(declined.pk, 20_000, charge=charge).status == CaptureStatus.CHARGED
        assert reload(declined).charge_blocked_reason == ""

        lost = expired_hold(fake_stripe, target=HoldableOrderFactory(user=order.user))
        lost_charge = Mock(side_effect=[connection_error(), "ch_lost"])
        with pytest.raises(stripe.APIConnectionError):
            capture(lost.pk, 20_000, charge=lost_charge)
        CardHold.objects.filter(pk=lost.pk).update(
            charge_claimed_at=timezone.now() - CHARGE_KEY_TTL - datetime.timedelta(minutes=1)
        )
        with caplog.at_level("ERROR", logger="baseapp_payments.holds"):
            assert capture(lost.pk, 20_000, charge=lost_charge).status == (
                CaptureStatus.NOT_CAPTURED
            )
        assert lost_charge.call_count == 1
        assert reload(lost).charge_blocked_reason == CardHold.ChargeBlock.STALE_CHARGE
        assert "got no usable answer" in caplog.text

    def test_a_kept_failed_hold_whose_charge_was_declined_is_charged_again(
        self, order, fake_stripe
    ) -> None:
        hold = CardHoldFactory(
            target=order,
            status=CardHold.Status.FAILED,
            stripe_payment_intent_id=None,
            kept_at=timezone.now(),
        )
        charge = Mock(side_effect=[card_declined(), "ch_new"])

        assert capture(hold.pk, 10_000, charge=charge).status == CaptureStatus.DECLINED
        assert capture(hold.pk, 10_000, charge=charge).status == CaptureStatus.CHARGED
        assert charge.call_count == 2

    def test_a_retry_claim_that_moved_on_charges_nothing(self, order, fake_stripe) -> None:
        hold = live_hold(fake_stripe, target=order)
        CardHold.objects.filter(pk=hold.pk).update(
            status=CardHold.Status.RELEASED,
            release_reason=CardHold.ReleaseReason.FOR_CHARGE,
            charge_generation=1,
        )
        seen = reload(hold)
        CardHold.objects.filter(pk=hold.pk).update(charge_generation=2)
        charge = Mock()

        assert holds._charge_again(seen, charge, 10_000).status == CaptureStatus.IN_PROGRESS
        charge.assert_not_called()


class TestAfterARefusedCharge:
    """A refused charge settles the hold (released ``for_charge``, a new generation), so
    release() and the sweep no longer touch it: the next capture() re-checks the target
    itself, and release_for_charge() leaves the charge to capture()."""

    def test_a_target_cancelled_after_a_decline_is_never_charged(
        self, order, fake_stripe, django_capture_on_commit_callbacks
    ) -> None:
        hold = expired_hold(fake_stripe, target=order)
        charge = Mock(side_effect=[card_declined(), "ch_new"])
        assert capture(hold.pk, 20_000, charge=charge).status == CaptureStatus.DECLINED
        order.status = HoldableOrder.Status.CANCELLED
        order.save()

        with django_capture_on_commit_callbacks(execute=True):
            sweep_card_holds()
        result = capture(hold.pk, 20_000, charge=charge)

        assert result.status == CaptureStatus.NOT_CAPTURED
        assert charge.call_count == 1
        hold = reload(hold)
        assert hold.charge_key == "" and hold.charged_at is None
        assert hold.charge_generation == 1

    def test_a_saved_card_whose_target_was_cancelled_after_a_decline_isnt_charged(
        self, order, fake_stripe
    ) -> None:
        """The no-hold direct charge goes through the same retry."""
        hold = CardHoldFactory(
            target=order, status=CardHold.Status.SAVED, stripe_payment_intent_id=None
        )
        charge = Mock(side_effect=[card_declined(), "ch_new"])
        assert capture(hold.pk, 10_000, charge=charge).status == CaptureStatus.DECLINED
        HoldableOrder.objects.filter(pk=order.pk).update(status=HoldableOrder.Status.CANCELLED)

        assert capture(hold.pk, 10_000, charge=charge).status == CaptureStatus.NOT_CAPTURED
        assert charge.call_count == 1

    def test_a_target_deleted_after_a_decline_is_never_charged(
        self, order, fake_stripe, django_capture_on_commit_callbacks
    ) -> None:
        hold = expired_hold(fake_stripe, target=order)
        charge = Mock(side_effect=[card_declined(), "ch_new"])
        assert capture(hold.pk, 20_000, charge=charge).status == CaptureStatus.DECLINED
        with django_capture_on_commit_callbacks(execute=True):
            order.delete()

        assert capture(hold.pk, 20_000, charge=charge).status == CaptureStatus.NOT_CAPTURED
        assert charge.call_count == 1

    def test_a_target_done_with_the_card_is_charged_again(self, order, fake_stripe) -> None:
        """Only a cancelled target stops the retry: one marked charged is what the retry
        is for."""
        hold = expired_hold(fake_stripe, target=order)
        charge = Mock(side_effect=[card_declined(), "ch_new"])
        assert capture(hold.pk, 20_000, charge=charge).status == CaptureStatus.DECLINED
        HoldableOrder.objects.filter(pk=order.pk).update(status=HoldableOrder.Status.CHARGED)

        assert capture(hold.pk, 20_000, charge=charge).status == CaptureStatus.CHARGED
        assert [call.kwargs["idempotency_key"] for call in charge.call_args_list] == [
            charge_idempotency_key(hold.pk, 0),
            charge_idempotency_key(hold.pk, 1),
        ]

    def test_release_for_charge_answers_false_and_changes_nothing(self, order, fake_stripe) -> None:
        hold = expired_hold(fake_stripe, target=order)
        charge = Mock(side_effect=[card_declined(), "ch_new"])
        assert capture(hold.pk, 20_000, charge=charge).status == CaptureStatus.DECLINED
        before = reload(hold)
        calls = len(fake_stripe.calls)

        assert release_for_charge(hold.pk) is False

        after = reload(hold)
        assert len(fake_stripe.calls) == calls
        assert after.release_reason == CardHold.ReleaseReason.FOR_CHARGE
        assert (after.charge_key, after.charge_generation, after.charged_at) == ("", 1, None)
        assert after.capture_claimed_at is None and after.modified == before.modified
        # capture() still owns the charge: it charges once, with the next key.
        assert capture(hold.pk, 20_000, charge=charge).status == CaptureStatus.CHARGED
        assert charge.call_count == 2


class TestCaptureOfNothingWithAnUnfinishedCharge:
    def test_it_answers_in_progress_and_never_re_runs_the_charge(
        self, order, fake_stripe, caplog
    ) -> None:
        hold = expired_hold(fake_stripe, target=order)
        charge = Mock(side_effect=[connection_error(), "ch_new"])
        with pytest.raises(stripe.APIConnectionError):
            capture(hold.pk, 20_000, charge=charge)
        before = reload(hold)

        with caplog.at_level("ERROR", logger="baseapp_payments.holds"):
            result = capture(hold.pk, 0, charge=charge)

        assert result.status == CaptureStatus.IN_PROGRESS
        assert charge.call_count == 1
        assert "settle it by hand" in caplog.text
        after = reload(hold)
        assert (after.charge_key, after.charge_claimed_at) == (
            before.charge_key,
            before.charge_claimed_at,
        )
        assert after.charged_at is None and after.charge_blocked_reason == ""
        assert after.capture_claimed_at is None

    def test_a_finished_or_blocked_charge_answers_as_before(self, order, fake_stripe) -> None:
        charged = live_hold(fake_stripe, target=order)
        CardHold.objects.filter(pk=charged.pk).update(
            status=CardHold.Status.RELEASED,
            charge_key=charge_idempotency_key(charged.pk),
            charge_claimed_at=timezone.now(),
            charged_at=timezone.now(),
        )
        blocked = live_hold(fake_stripe, target=HoldableOrderFactory(user=order.user))
        CardHold.objects.filter(pk=blocked.pk).update(
            status=CardHold.Status.RELEASED,
            charge_key=charge_idempotency_key(blocked.pk),
            charge_claimed_at=timezone.now(),
            charge_blocked_reason=CardHold.ChargeBlock.STALE_CHARGE,
        )
        charge = Mock()

        assert capture(charged.pk, 0, charge=charge).status == CaptureStatus.CHARGED
        assert capture(blocked.pk, 0, charge=charge).status == CaptureStatus.NOT_CAPTURED
        charge.assert_not_called()
