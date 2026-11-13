"""Targets without holds (``uses_holds = False``: the card is saved and charged on the
date) and targets charged now (no date after today: no hold at all)."""

import datetime
import uuid
from typing import Any
from unittest.mock import Mock

import pytest
import stripe
import swapper
from constance.test import override_config
from django.utils import timezone

from baseapp_payments.holds import (
    CaptureStatus,
    PlacementResult,
    PlacementStatus,
    authorize_on_session,
    capture,
    card_in_use,
    charge_idempotency_key,
    complete_setup_on_session,
    find_placed,
    release,
    release_for_charge,
)
from baseapp_payments.tasks import sweep_card_holds
from testproject.testapp.card_holds import HoldableOrderHoldTarget
from testproject.testapp.models import HoldableOrder

from ..factories import CardHoldFactory, HoldableOrderFactory
from ..fakes import STRIPE_CUSTOMER_ID, project_charge

CardHold = swapper.load_model("baseapp_payments", "CardHold")

pytestmark = pytest.mark.django_db


@pytest.fixture
def direct_charge(monkeypatch) -> None:
    """The test project's adapter, declared without holds."""
    monkeypatch.setattr(HoldableOrderHoldTarget, "uses_holds", False)


def days(count: int) -> datetime.date:
    return timezone.localdate() + datetime.timedelta(days=count)


def place(holder, order: HoldableOrder, attempt_id=None, **kwargs) -> PlacementResult:
    kwargs.setdefault("payment_method_id", "pm_visa")
    kwargs.setdefault("expected_amount_cents", order.amount_cents)

    def link(hold) -> HoldableOrder:
        order.save()
        return order

    return authorize_on_session(
        user=holder,
        attempt_id=attempt_id or uuid.uuid4(),
        stripe_customer_id=STRIPE_CUSTOMER_ID,
        target=order,
        link=None if order.pk else link,
        **kwargs,
    )


@pytest.fixture
def saved(holder, fake_stripe, direct_charge) -> Any:
    """A target in ten days whose card was saved, nothing held."""
    order = HoldableOrder(user=holder, amount_cents=10_000, target_date=days(10))
    result = place(holder, order)
    assert result.status == PlacementStatus.CARD_SAVED
    return result.hold


class TestCardSaved:
    @pytest.mark.parametrize("deferral", [False, True])
    def test_a_future_target_saves_the_card_and_authorizes_nothing(
        self, holder, fake_stripe, direct_charge, deferral
    ) -> None:
        """Product change 1: whatever the deferral setting or the date."""
        order = HoldableOrder(user=holder, amount_cents=10_000, target_date=days(30))
        attempt_id = uuid.uuid4()

        with override_config(CARD_HOLDS_DEFERRAL_ENABLED=deferral):
            result = place(holder, order, attempt_id)

        assert result.status == PlacementStatus.CARD_SAVED
        assert result.target == order and order.pk is not None
        assert result.hold_on is None
        assert fake_stripe.calls_to("PaymentIntent.create") == []
        ((_args, params),) = fake_stripe.calls_to("SetupIntent.create")
        assert params["usage"] == "off_session"
        assert params["idempotency_key"] == f"testproject-setup-{holder.pk}-{attempt_id}"
        hold = CardHold.objects.get()
        assert hold.status == CardHold.Status.SAVED
        assert hold.target == order
        assert (hold.estimated_amount_cents, hold.buffer_percent, hold.amount_cents) == (
            10_000,
            0,
            0,
        )
        assert hold.hold_on is None and hold.expires_at is None
        assert card_in_use(holder, "pm_visa")

    def test_a_retry_answers_card_saved_from_the_database(
        self, holder, fake_stripe, direct_charge
    ) -> None:
        attempt_id = uuid.uuid4()
        first = place(holder, HoldableOrder(user=holder, target_date=days(10)), attempt_id)
        calls = len(fake_stripe.calls)

        again = place(holder, HoldableOrder(user=holder, target_date=days(10)), attempt_id)

        assert again.status == PlacementStatus.CARD_SAVED
        assert again.target == first.target
        assert find_placed(holder, attempt_id) == first.target
        assert len(fake_stripe.calls) == calls

    def test_authenticating_the_saved_card_takes_a_second_pass(
        self, holder, fake_stripe, direct_charge
    ) -> None:
        fake_stripe.next_setup_outcome = ["requires_action"]
        attempt_id = uuid.uuid4()
        order = HoldableOrder(user=holder, amount_cents=10_000, target_date=days(10))

        first = place(holder, order, attempt_id)
        assert first.status == PlacementStatus.REQUIRES_ACTION
        assert first.intent_type == "setup_intent"
        (setup_intent_id,) = fake_stripe.setup_intents
        fake_stripe.attach(setup_intent_id)

        def link(hold) -> HoldableOrder:
            order.save()
            return order

        second = complete_setup_on_session(
            setup_intent_id,
            link,
            user=holder,
            attempt_id=attempt_id,
            stripe_customer_id=STRIPE_CUSTOMER_ID,
            expected_amount_cents=10_000,
        )

        assert second.status == PlacementStatus.CARD_SAVED
        assert CardHold.objects.get().status == CardHold.Status.SAVED

    def test_the_sweep_never_places_a_saved_card(self, saved, fake_stripe) -> None:
        CardHold.objects.filter(pk=saved.pk).update(hold_on=timezone.localdate())

        with override_config(CARD_HOLDS_DEFERRAL_ENABLED=True):
            sweep_card_holds()

        saved.refresh_from_db()
        assert saved.status == CardHold.Status.SAVED
        assert fake_stripe.calls_to("PaymentIntent.create") == []

    def test_an_existing_targets_released_row_is_saved_again(
        self, holder, fake_stripe, direct_charge
    ) -> None:
        order = HoldableOrderFactory(user=holder, target_date=days(10))
        previous = CardHoldFactory(
            target=order,
            status=CardHold.Status.RELEASED,
            stripe_payment_intent_id="pi_old",
            release_confirmed_at=timezone.now(),
            charge_blocked_reason=CardHold.ChargeBlock.DECLINED,
        )

        result = place(holder, order)

        assert result.status == PlacementStatus.CARD_SAVED
        previous.refresh_from_db()
        assert previous.status == CardHold.Status.SAVED
        assert previous.previous_payment_intent_ids == ["pi_old"]
        assert previous.charge_blocked_reason == ""
        assert CardHold.objects.count() == 1


class TestChargedOnTheDate:
    def test_capture_charges_the_saved_card_once(self, saved, fake_stripe) -> None:
        calls = len(fake_stripe.calls)
        charge = Mock(return_value="ch_new")

        first = capture(saved.pk, 10_500, charge=charge)
        again = capture(saved.pk, 10_500, charge=charge)

        assert first.status == again.status == CaptureStatus.CHARGED
        assert first.charge == "ch_new" and again.charge is None
        charge.assert_called_once_with(idempotency_key=charge_idempotency_key(saved.pk))
        assert len(fake_stripe.calls) == calls
        saved.refresh_from_db()
        assert saved.status == CardHold.Status.RELEASED
        assert saved.release_reason == CardHold.ReleaseReason.FOR_CHARGE
        assert saved.charged_at is not None and saved.charge_claimed_at is not None

    def test_a_charge_that_raised_is_retried_with_its_key(self, saved, fake_stripe) -> None:
        charge = Mock(side_effect=[stripe.APIConnectionError("lost"), "ch_new"])

        with pytest.raises(stripe.APIConnectionError):
            capture(saved.pk, 10_000, charge=charge)
        result = capture(saved.pk, 10_000, charge=charge)

        assert result.status == CaptureStatus.CHARGED
        keys = [call.kwargs["idempotency_key"] for call in charge.call_args_list]
        assert keys == [charge_idempotency_key(saved.pk)] * 2

    def test_a_cancelled_target_releases_it_without_stripe_and_charges_nothing(
        self, saved, fake_stripe
    ) -> None:
        order = saved.target
        order.status = HoldableOrder.Status.CANCELLED
        order.save()
        calls = len(fake_stripe.calls)

        assert release(saved.pk) is True
        saved.refresh_from_db()
        assert saved.status == CardHold.Status.RELEASED
        assert saved.release_confirmed_at is not None
        assert len(fake_stripe.calls) == calls
        assert not card_in_use(saved.customer, "pm_visa")
        charge = Mock()
        assert capture(saved.pk, 10_000, charge=charge).status == CaptureStatus.NOT_CAPTURED
        charge.assert_not_called()

    def test_release_for_charge_hands_the_charge_to_its_caller(self, saved, fake_stripe) -> None:
        assert release_for_charge(saved.pk) is True
        charge = Mock()

        assert capture(saved.pk, 10_000, charge=charge).status == CaptureStatus.NOT_CAPTURED
        charge.assert_not_called()


class TestChargeNow:
    """Product change 3: a hold is only for a target charged in the future."""

    @pytest.mark.parametrize("uses_holds", [True, False])
    @pytest.mark.parametrize("offset", [None, 0, -3])
    def test_a_target_charged_now_takes_no_hold(
        self, holder, fake_stripe, monkeypatch, uses_holds, offset
    ) -> None:
        monkeypatch.setattr(HoldableOrderHoldTarget, "uses_holds", uses_holds)
        when = None if offset is None else days(offset)
        order = HoldableOrder(user=holder, amount_cents=10_000, target_date=when)

        with override_config(CARD_HOLDS_DEFERRAL_ENABLED=True):
            result = place(holder, order)

        assert result.status == PlacementStatus.CHARGE_NOW
        assert result.target is order and order.pk is None
        assert fake_stripe.calls == []
        assert not CardHold.objects.exists()

    def test_tomorrow_is_held(self, holder, fake_stripe) -> None:
        result = place(holder, HoldableOrder(user=holder, amount_cents=10_000, target_date=days(1)))

        assert result.status == PlacementStatus.PLACED

    def test_an_existing_target_dated_today_takes_no_hold_either(self, holder, fake_stripe) -> None:
        order = HoldableOrderFactory(user=holder, target_date=days(0))

        assert place(holder, order).status == PlacementStatus.CHARGE_NOW
        assert fake_stripe.calls == []


class TestADeclinedDirectChargeIsRetriedWithANewKey:
    def test_a_decline_then_a_new_card_charges_once_with_the_next_key(
        self, saved, fake_stripe
    ) -> None:
        """#1 on the no-hold path: the decline doesn't lock the saved card's target."""
        fake_stripe.next_outcome = ["card_declined"]

        first = capture(saved.pk, 10_000, charge=project_charge(fake_stripe))
        retried = capture(
            saved.pk, 10_000, charge=project_charge(fake_stripe, payment_method="pm_new")
        )
        again = capture(saved.pk, 10_000, charge=project_charge(fake_stripe))

        assert first.status == CaptureStatus.DECLINED
        assert isinstance(first.error, stripe.CardError)
        assert retried.status == again.status == CaptureStatus.CHARGED
        keys = [params["idempotency_key"] for _args, params in creates(fake_stripe)]
        assert keys == [charge_idempotency_key(saved.pk, 0), charge_idempotency_key(saved.pk, 1)]
        saved.refresh_from_db()
        assert saved.charge_generation == 1 and saved.charged_at is not None
        assert saved.charge_key == charge_idempotency_key(saved.pk, 1)
        assert saved.charge_blocked_reason == ""


def creates(fake_stripe) -> list[tuple[tuple, dict]]:
    return fake_stripe.calls_to("PaymentIntent.create")
