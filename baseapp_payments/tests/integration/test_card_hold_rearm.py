"""Re-arming a target's released hold on the same row (one hold per target)."""

import datetime
import uuid
from typing import Any
from unittest.mock import patch

import pytest
import swapper
from django.utils import timezone

from baseapp_payments import holds
from baseapp_payments.holds import (
    PlacementResult,
    PlacementStatus,
    authorize_on_session,
    complete_on_session,
    find_placed,
    release,
)
from testproject.testapp.models import HoldableOrder

from ..factories import CardHoldFactory
from ..fakes import STRIPE_CUSTOMER_ID

CardHold = swapper.load_model("baseapp_payments", "CardHold")

pytestmark = pytest.mark.django_db


def released_hold(order: HoldableOrder, **fields: Any) -> Any:
    """A released hold of ``order`` whose cancel Stripe confirmed (unless ``fields`` say
    otherwise): only those are re-armed at once."""
    fields.setdefault("release_confirmed_at", timezone.now())
    return CardHoldFactory(
        target=order,
        status=CardHold.Status.RELEASED,
        stripe_payment_intent_id="pi_old",
        # A failure code without failed_at: a deferred hold that failed and was cancelled
        # by staff (failed_at set) is final and never re-armed.
        failure_code="card_declined",
        placement_key="key-old",
        placement_amount_cents=11_000,
        placement_claimed_at=timezone.now(),
        **fields,
    )


def hold_again(order: HoldableOrder, attempt_id: Any, **kwargs: Any) -> PlacementResult:
    kwargs.setdefault("payment_method_id", "pm_visa")
    return authorize_on_session(
        user=order.user,
        attempt_id=attempt_id,
        stripe_customer_id=STRIPE_CUSTOMER_ID,
        target=order,
        expected_amount_cents=order.amount_cents,
        **kwargs,
    )


class TestRearm:
    def test_a_released_hold_is_re_armed_on_the_same_row(self, order, fake_stripe) -> None:
        previous = released_hold(order)
        fake_stripe.add_card("pm_mc", brand="mastercard", last4="4444", funding="debit")
        attempt_id = uuid.uuid4()

        result = hold_again(order, attempt_id, payment_method_id="pm_mc")

        assert result.status == PlacementStatus.PLACED
        assert result.target == order
        (hold,) = CardHold.objects.all()
        assert hold.pk == previous.pk
        (new_payment_intent_id,) = fake_stripe.intents
        assert hold.stripe_payment_intent_id == new_payment_intent_id
        assert hold.previous_payment_intent_ids == ["pi_old"]
        assert hold.status == CardHold.Status.AUTHORIZED
        assert hold.attempt_id == attempt_id
        assert (hold.card_brand, hold.card_last4, hold.card_funding) == (
            "mastercard",
            "4444",
            "debit",
        )
        assert (hold.estimated_amount_cents, hold.amount_cents) == (10_000, 11_000)
        assert hold.expires_at > timezone.now()
        assert hold.failed_at is None and hold.failure_code == ""
        assert hold.placement_key == "" and hold.placement_amount_cents is None
        assert hold.placement_claimed_at is None
        assert find_placed(order.user, attempt_id) == order

    def test_the_audit_list_grows_with_each_re_arm(self, order, fake_stripe) -> None:
        released_hold(order)
        hold_again(order, uuid.uuid4())
        first = CardHold.objects.get().stripe_payment_intent_id
        CardHold.objects.update(status=CardHold.Status.RELEASED)

        hold_again(order, uuid.uuid4())

        hold = CardHold.objects.get()
        assert hold.previous_payment_intent_ids == ["pi_old", first]
        assert hold.stripe_payment_intent_id not in hold.previous_payment_intent_ids

    def test_the_second_pass_re_arms_too(self, order, fake_stripe) -> None:
        previous = released_hold(order)
        attempt_id = uuid.uuid4()
        fake_stripe.next_outcome = ["requires_action"]
        assert hold_again(order, attempt_id).status == PlacementStatus.REQUIRES_ACTION
        (payment_intent_id,) = fake_stripe.intents
        assert CardHold.objects.count() == 2  # the pending row, until it is folded in
        fake_stripe.set_status(payment_intent_id, "requires_capture")

        result = complete_on_session(
            payment_intent_id,
            user=order.user,
            attempt_id=attempt_id,
            stripe_customer_id=STRIPE_CUSTOMER_ID,
            target=order,
            expected_amount_cents=10_000,
        )

        assert result.status == PlacementStatus.PLACED
        (hold,) = CardHold.objects.all()
        assert hold.pk == previous.pk
        assert hold.stripe_payment_intent_id == payment_intent_id

    @pytest.mark.parametrize("status", ["pending", "authorized", "captured", "failed", "scheduled"])
    def test_any_other_previous_hold_refuses_before_stripe(
        self, order, fake_stripe, status
    ) -> None:
        previous = released_hold(order)
        CardHold.objects.filter(pk=previous.pk).update(status=status)

        result = hold_again(order, uuid.uuid4())

        assert result.status == PlacementStatus.REFUSED
        assert fake_stripe.calls == []
        previous.refresh_from_db()
        assert previous.status == status and previous.stripe_payment_intent_id == "pi_old"

    @pytest.mark.parametrize(
        "fields",
        [
            {"release_reason": "for_charge"},
            {"charge_key": "testproject-charge-1"},
            {"charged_at": datetime.datetime(2030, 1, 1, tzinfo=datetime.timezone.utc)},
        ],
    )
    def test_a_hold_released_to_charge_afresh_is_never_re_armed(
        self, order, fake_stripe, django_capture_on_commit_callbacks, fields
    ) -> None:
        """N1: the early check and the check under the lock both refuse."""
        previous = released_hold(order, **fields)

        assert hold_again(order, uuid.uuid4()).status == PlacementStatus.REFUSED
        assert fake_stripe.calls == []

        with (
            patch.object(holds, "_may_hold", return_value=None),
            django_capture_on_commit_callbacks(execute=True),
        ):
            assert hold_again(order, uuid.uuid4()).status == PlacementStatus.REFUSED
        previous.refresh_from_db()
        assert previous.stripe_payment_intent_id == "pi_old"

    @pytest.mark.parametrize("reason", ["cancelled", "declined", "lapsed", ""])
    def test_any_other_release_reason_re_arms(self, order, fake_stripe, reason) -> None:
        previous = released_hold(order, release_reason=reason)

        assert hold_again(order, uuid.uuid4()).status == PlacementStatus.PLACED
        previous.refresh_from_db()
        assert previous.status == CardHold.Status.AUTHORIZED
        assert previous.release_reason == ""

    @pytest.mark.parametrize("status", ["authorized", "captured"])
    def test_under_the_lock_an_open_or_captured_hold_still_refuses(
        self, order, fake_stripe, django_capture_on_commit_callbacks, status
    ) -> None:
        previous = released_hold(order)
        CardHold.objects.filter(pk=previous.pk).update(status=status)

        # The early check passed before the hold changed: the lock decides.
        with (
            patch.object(holds, "_may_hold", return_value=None),
            django_capture_on_commit_callbacks(execute=True),
        ):
            result = hold_again(order, uuid.uuid4())

        assert result.status == PlacementStatus.REFUSED
        previous.refresh_from_db()
        assert previous.status == status and previous.stripe_payment_intent_id == "pi_old"
        (new_payment_intent_id,) = fake_stripe.intents
        assert fake_stripe.status_of(new_payment_intent_id) == "canceled"
        assert CardHold.objects.get(stripe_payment_intent_id=new_payment_intent_id).status == (
            CardHold.Status.RELEASED
        )

    def test_a_target_from_link_is_not_re_armed_without_its_lock(self, order, fake_stripe) -> None:
        released_hold(order)

        result = authorize_on_session(
            user=order.user,
            attempt_id=uuid.uuid4(),
            payment_method_id="pm_visa",
            stripe_customer_id=STRIPE_CUSTOMER_ID,
            target=HoldableOrder(
                user=order.user, amount_cents=10_000, target_date=order.target_date
            ),
            link=lambda hold: order,
            expected_amount_cents=10_000,
        )

        assert result.status == PlacementStatus.REFUSED
        assert CardHold.objects.get(target_document__isnull=False).stripe_payment_intent_id == (
            "pi_old"
        )

    def test_a_late_release_of_the_old_authorization_spares_the_new_one(
        self, order, fake_stripe
    ) -> None:
        previous = released_hold(order)
        fake_stripe.intents["pi_old"] = {
            "id": "pi_old",
            "status": "requires_capture",
            "amount": 11_000,
            "payment_method": "pm_visa",
            "capture_before": None,
        }
        hold_again(order, uuid.uuid4())
        new_payment_intent_id = CardHold.objects.get().stripe_payment_intent_id

        # The release queued when the old hold was claimed only runs now.
        assert release(previous.pk, claimed=True, payment_intent_id="pi_old") is True

        assert fake_stripe.status_of("pi_old") == "canceled"
        assert fake_stripe.status_of(new_payment_intent_id) == "requires_capture"
        hold = CardHold.objects.get()
        assert hold.status == CardHold.Status.AUTHORIZED
        assert hold.stripe_payment_intent_id == new_payment_intent_id

    def test_mark_released_is_scoped_to_the_authorization(self, order) -> None:
        hold = CardHoldFactory(target=order, expires_at=timezone.now() + datetime.timedelta(1))

        assert holds.mark_released(hold.pk, "pi_other") is False
        assert holds.mark_released(hold.pk, hold.stripe_payment_intent_id) is True


class TestPendingRowFoldedInMeanwhile:
    """A second pass that waited on a pending row a concurrent re-arm deleted."""

    def complete(self, payment_intent_id: str) -> PlacementResult:
        return holds._complete(
            payment_intent=holds.retrieve_payment_intent(payment_intent_id),
            link=None,
            target=None,
            expected_amount_cents=10_000,
        )

    def first_lookup_misses(self) -> Any:
        manager = type(CardHold.objects)
        original = manager.select_for_update
        calls: list[int] = []

        def select_for_update(self: Any, *args: Any, **kwargs: Any) -> Any:
            calls.append(1)
            queryset = original(self, *args, **kwargs)
            return queryset.none() if len(calls) == 1 else queryset

        return patch.object(manager, "select_for_update", select_for_update)

    def test_the_re_armed_hold_is_found_again(self, order, fake_stripe) -> None:
        hold = CardHoldFactory(target=order, stripe_payment_intent_id="pi_new")
        fake_stripe.intents["pi_new"] = {
            "id": "pi_new",
            "status": "requires_capture",
            "amount": 11_000,
            "payment_method": "pm_visa",
            "capture_before": None,
        }

        with self.first_lookup_misses():
            result = self.complete("pi_new")

        assert result.status == PlacementStatus.PLACED
        assert result.target == order and result.hold == hold
        assert fake_stripe.calls_to("PaymentIntent.cancel") == []

    def test_a_payment_intent_with_no_row_at_all_declines_untouched(self, fake_stripe) -> None:
        fake_stripe.intents["pi_lost"] = {
            "id": "pi_lost",
            "status": "requires_capture",
            "amount": 11_000,
            "payment_method": "pm_visa",
            "capture_before": None,
        }

        result = self.complete("pi_lost")

        assert result.status == PlacementStatus.DECLINED
        assert fake_stripe.calls_to("PaymentIntent.cancel") == []


class TestAnUnconfirmedReleaseIsntDropped:
    """M1: re-arming replaced the PaymentIntent of a hold whose cancel Stripe hadn't
    confirmed, so the old authorization stayed live and nothing tracked it any more."""

    def live_old(self, fake_stripe) -> None:
        fake_stripe.intents["pi_old"] = {
            "id": "pi_old",
            "object": "payment_intent",
            "status": "requires_capture",
            "amount": 11_000,
            "payment_method": "pm_visa",
            "capture_before": None,
            "amount_received": 0,
        }

    def test_the_old_authorization_is_cancelled_before_the_re_arm(self, order, fake_stripe) -> None:
        """Reviewer's repro: released, cancel never confirmed (the task gave up)."""
        self.live_old(fake_stripe)
        previous = released_hold(order, release_reason="cancelled", release_confirmed_at=None)

        result = hold_again(order, uuid.uuid4())

        assert result.status == PlacementStatus.PLACED
        assert fake_stripe.status_of("pi_old") == "canceled"
        cancels = [args[0] for args, _kw in fake_stripe.calls_to("PaymentIntent.cancel")]
        assert cancels == ["pi_old"]
        # Stripe was asked before the new authorization was made.
        names = [name for name, _a, _k in fake_stripe.calls]
        assert names.index("PaymentIntent.cancel") < names.index("PaymentIntent.create")
        previous.refresh_from_db()
        assert previous.previous_payment_intent_ids == ["pi_old"]

    def test_a_cancel_stripe_doesnt_confirm_is_in_progress(self, order, fake_stripe) -> None:
        from ..fakes import connection_error

        self.live_old(fake_stripe)
        previous = released_hold(order, release_confirmed_at=None)
        fake_stripe.fail_next("PaymentIntent.cancel", connection_error())

        result = hold_again(order, uuid.uuid4())

        assert result.status == PlacementStatus.IN_PROGRESS
        assert fake_stripe.calls_to("PaymentIntent.create") == []
        previous.refresh_from_db()
        assert previous.stripe_payment_intent_id == "pi_old"
        assert previous.release_confirmed_at is None
        assert fake_stripe.status_of("pi_old") == "requires_capture"

    def test_a_cancel_stripe_refuses_is_in_progress(self, order, fake_stripe) -> None:
        from ..fakes import unexpected_state

        self.live_old(fake_stripe)
        released_hold(order, release_confirmed_at=None)
        fake_stripe.fail_next(
            "PaymentIntent.cancel", unexpected_state("pi_old", "processing", "cancel")
        )

        assert hold_again(order, uuid.uuid4()).status == PlacementStatus.IN_PROGRESS
        assert fake_stripe.calls_to("PaymentIntent.create") == []

    def test_under_the_lock_an_unconfirmed_release_is_in_progress_and_kept_pending(
        self, order, fake_stripe
    ) -> None:
        """The early check passed, then the release became unconfirmed again (another
        re-drive): the lock refuses to re-arm, keeps the new pending row for the same
        attempt, and a retry carries on once Stripe confirms."""
        self.live_old(fake_stripe)
        previous = released_hold(order, release_confirmed_at=None)
        attempt_id = uuid.uuid4()

        with patch.object(holds, "_may_hold", return_value=None):
            result = hold_again(order, attempt_id)

        assert result.status == PlacementStatus.IN_PROGRESS
        previous.refresh_from_db()
        assert previous.stripe_payment_intent_id == "pi_old"
        pending = CardHold.objects.exclude(pk=previous.pk).get()
        assert pending.status == CardHold.Status.PENDING
        assert pending.target_document_id is None

        again = hold_again(order, attempt_id)

        assert again.status == PlacementStatus.PLACED
        previous.refresh_from_db()
        assert previous.stripe_payment_intent_id == pending.stripe_payment_intent_id
        assert fake_stripe.status_of("pi_old") == "canceled"
        assert len(fake_stripe.intents) == 2  # replayed, not authorized twice
