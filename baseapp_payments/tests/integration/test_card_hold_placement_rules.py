"""Placement rules from the review: the second pass's statuses (M3), holdable targets
(M4), the re-arm lock (m1), attempt idempotency from the database (m2, m3), and placing
outside a transaction (m8)."""

import uuid
from typing import Any
from unittest.mock import patch

import pytest
import swapper
from django.db import transaction

from baseapp_core.models import DocumentId
from baseapp_payments import holds
from baseapp_payments.holds import (
    CardHoldInTransaction,
    PlacementResult,
    PlacementStatus,
    authorize_on_session,
    complete_on_session,
    find_attempt,
    find_placed,
)
from testproject.testapp.card_holds import HoldableOrderHoldTarget
from testproject.testapp.models import HoldableOrder

from ..factories import CardHoldFactory, HoldableOrderFactory
from ..fakes import STRIPE_CUSTOMER_ID

CardHold = swapper.load_model("baseapp_payments", "CardHold")

pytestmark = pytest.mark.django_db


def hold_existing(order: HoldableOrder, attempt_id: Any = None, **kwargs: Any) -> PlacementResult:
    return authorize_on_session(
        user=order.user,
        attempt_id=attempt_id or uuid.uuid4(),
        payment_method_id="pm_visa",
        stripe_customer_id=STRIPE_CUSTOMER_ID,
        target=order,
        expected_amount_cents=order.amount_cents,
        **kwargs,
    )


def requires_action(order: HoldableOrder, attempt_id: Any, fake_stripe: Any) -> str:
    fake_stripe.next_outcome = ["requires_action"]
    assert hold_existing(order, attempt_id).status == PlacementStatus.REQUIRES_ACTION
    (payment_intent_id,) = fake_stripe.intents
    return payment_intent_id


def second_pass(order: HoldableOrder, attempt_id: Any, payment_intent_id: str) -> PlacementResult:
    return complete_on_session(
        payment_intent_id,
        user=order.user,
        attempt_id=attempt_id,
        stripe_customer_id=STRIPE_CUSTOMER_ID,
        target=order,
        expected_amount_cents=order.amount_cents,
    )


class TestSecondPassStatuses:
    @pytest.mark.parametrize("status", ["requires_action", "requires_confirmation", "processing"])
    def test_a_payment_intent_still_waiting_is_in_progress_and_untouched(
        self, order, fake_stripe, django_capture_on_commit_callbacks, status
    ) -> None:
        attempt_id = uuid.uuid4()
        payment_intent_id = requires_action(order, attempt_id, fake_stripe)
        fake_stripe.set_status(payment_intent_id, status)

        with django_capture_on_commit_callbacks(execute=True):
            result = second_pass(order, attempt_id, payment_intent_id)

        assert result.status == PlacementStatus.IN_PROGRESS
        assert fake_stripe.status_of(payment_intent_id) == status
        assert fake_stripe.calls_to("PaymentIntent.cancel") == []
        assert CardHold.objects.get().status == CardHold.Status.PENDING

    @pytest.mark.parametrize("status", ["canceled", "requires_payment_method"])
    def test_only_a_finished_payment_intent_is_abandoned(
        self, order, fake_stripe, django_capture_on_commit_callbacks, status
    ) -> None:
        attempt_id = uuid.uuid4()
        payment_intent_id = requires_action(order, attempt_id, fake_stripe)
        fake_stripe.set_status(payment_intent_id, status)

        with django_capture_on_commit_callbacks(execute=True):
            result = second_pass(order, attempt_id, payment_intent_id)

        assert result.status == PlacementStatus.DECLINED
        assert CardHold.objects.get().status == CardHold.Status.RELEASED


class TestHoldableTargets:
    @pytest.mark.parametrize(
        "status", [HoldableOrder.Status.CANCELLED, HoldableOrder.Status.CHARGED]
    )
    def test_a_cancelled_or_charged_target_is_refused_before_stripe(
        self, holder, fake_stripe, status
    ) -> None:
        order = HoldableOrderFactory(user=holder, status=status)

        assert hold_existing(order).status == PlacementStatus.REFUSED
        assert fake_stripe.calls == []

    def test_a_target_outside_filter_holdable_is_refused_before_stripe(
        self, order, fake_stripe
    ) -> None:
        with patch.object(
            HoldableOrderHoldTarget, "filter_holdable", lambda self, queryset: queryset.none()
        ):
            assert hold_existing(order).status == PlacementStatus.REFUSED
        assert fake_stripe.calls == []

    def test_a_target_cancelled_after_the_early_check_is_refused_under_the_lock(
        self, order, fake_stripe, django_capture_on_commit_callbacks
    ) -> None:
        original = holds._may_hold

        def cancel_meanwhile(target: Any) -> bool:
            allowed = original(target)
            HoldableOrder.objects.filter(pk=order.pk).update(status=HoldableOrder.Status.CANCELLED)
            return allowed

        with (
            patch.object(holds, "_may_hold", side_effect=cancel_meanwhile),
            django_capture_on_commit_callbacks(execute=True),
        ):
            result = hold_existing(order)

        assert result.status == PlacementStatus.REFUSED
        (payment_intent_id,) = fake_stripe.intents
        assert fake_stripe.status_of(payment_intent_id) == "canceled"
        assert CardHold.objects.get().target_document is None

    def test_a_released_hold_on_a_cancelled_target_is_not_re_armed(
        self, order, fake_stripe
    ) -> None:
        CardHoldFactory(target=order, status=CardHold.Status.RELEASED)
        order.status = HoldableOrder.Status.CANCELLED
        order.save()

        assert hold_existing(order).status == PlacementStatus.REFUSED
        assert fake_stripe.calls == []


class TestRearmLock:
    def test_link_returning_another_target_never_re_arms_it(self, holder, fake_stripe) -> None:
        locked = HoldableOrderFactory(user=holder)
        other = HoldableOrderFactory(user=holder)
        CardHoldFactory(
            target=locked, status=CardHold.Status.RELEASED, stripe_payment_intent_id="pi_a"
        )
        CardHoldFactory(
            target=other, status=CardHold.Status.RELEASED, stripe_payment_intent_id="pi_b"
        )

        result = hold_existing(locked, link=lambda hold: other)

        assert result.status == PlacementStatus.REFUSED
        assert set(
            CardHold.objects.filter(target_document__isnull=False).values_list(
                "stripe_payment_intent_id", flat=True
            )
        ) == {"pi_a", "pi_b"}


class TestAttemptIdempotency:
    def test_the_original_attempt_still_finds_a_re_armed_target(self, order, fake_stripe) -> None:
        first_attempt = uuid.uuid4()
        CardHoldFactory(target=order, status=CardHold.Status.RELEASED, attempt_id=first_attempt)
        second_attempt = uuid.uuid4()
        assert hold_existing(order, second_attempt).status == PlacementStatus.PLACED
        calls = len(fake_stripe.calls)

        retried = hold_existing(order, first_attempt)

        assert retried.status == PlacementStatus.PLACED
        assert retried.target == order
        assert find_placed(order.user, first_attempt) == order
        assert CardHold.objects.get().previous_attempt_ids == [str(first_attempt)]
        assert len(fake_stripe.calls) == calls

    def test_an_attempt_that_ended_without_a_target_declines_after_stripe_forgot(
        self, holder, fake_stripe
    ) -> None:
        attempt_id = uuid.uuid4()
        CardHoldFactory(customer=holder, attempt_id=attempt_id, status=CardHold.Status.RELEASED)
        fake_stripe.replies.clear()  # Stripe's 24-hour idempotency window has passed

        result = hold_existing(HoldableOrder(user=holder, amount_cents=10_000), attempt_id)

        assert result.status == PlacementStatus.DECLINED
        assert fake_stripe.calls == []

    def test_an_attempt_whose_target_was_deleted_declines(self, order, fake_stripe) -> None:
        attempt_id = uuid.uuid4()
        hold = CardHoldFactory(target=order, attempt_id=attempt_id)
        CardHold.objects.filter(pk=hold.pk).update(
            target_document=DocumentId.objects.create(
                content_type=hold.target_document.content_type, object_id=order.pk + 99_999
            )
        )

        found = find_attempt(order.user, attempt_id)

        assert found is not None and found.status == PlacementStatus.DECLINED
        assert find_placed(order.user, attempt_id) is None

    def test_a_pending_attempt_carries_on(self, holder) -> None:
        attempt_id = uuid.uuid4()
        CardHoldFactory(customer=holder, attempt_id=attempt_id, status=CardHold.Status.PENDING)

        assert find_attempt(holder, attempt_id) is None

    def test_a_placed_attempt_answers_whatever_its_hold_status(self, order) -> None:
        attempt_id = uuid.uuid4()
        CardHoldFactory(target=order, attempt_id=attempt_id, status=CardHold.Status.CAPTURED)

        assert find_placed(order.user, attempt_id) == order


class TestOutsideATransaction:
    """S4: the guard reads Django's public ``get_autocommit()``; the test project turns it
    off for the transaction every ``db`` test runs in, so these use a real database."""

    @pytest.fixture(autouse=True)
    def guard_on(self, settings) -> None:
        settings.BASEAPP_PAYMENTS_CARD_HOLD_REQUIRE_AUTOCOMMIT = True

    @pytest.mark.django_db(transaction=True)
    def test_placing_outside_a_transaction_is_allowed(self, order, fake_stripe) -> None:
        assert hold_existing(order).status == PlacementStatus.PLACED

    @pytest.mark.django_db(transaction=True)
    def test_placing_inside_atomic_raises(self, order, fake_stripe) -> None:
        with transaction.atomic(), pytest.raises(CardHoldInTransaction):
            hold_existing(order)
        with transaction.atomic(), pytest.raises(CardHoldInTransaction):
            second_pass(order, uuid.uuid4(), "pi_any")
        assert fake_stripe.calls == []
