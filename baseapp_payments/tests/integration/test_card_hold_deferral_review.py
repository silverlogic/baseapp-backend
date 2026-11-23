"""Deferred holds: a bad API key is no answer (M2), a placement left unsettled by a
deleted target is still settled (M4), and turning deferral off stops every new
off-session placement (m1)."""

import datetime
from collections.abc import Generator
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
    _place_if_due,
    capture,
    charge_idempotency_key,
    place_scheduled,
    release,
    release_for_charge,
    reschedule_hold,
)
from baseapp_payments.tasks import reschedule_card_hold, sweep_card_holds

from ..factories import CardHoldFactory, HoldableOrderFactory, UserFactory
from ..fakes import connection_error
from ..helpers import grant_card_hold_perm

CardHold = swapper.load_model("baseapp_payments", "CardHold")

pytestmark = pytest.mark.django_db


@pytest.fixture
def deferral() -> Generator[None, None, None]:
    with override_config(CARD_HOLDS_DEFERRAL_ENABLED=True):
        yield


def days(count: int) -> datetime.date:
    return timezone.localdate() + datetime.timedelta(days=count)


def due(holder, **fields) -> Any:
    """A scheduled hold whose day is today."""
    order = HoldableOrderFactory(user=holder, target_date=days(4))
    return CardHoldFactory(
        target=order,
        stripe_payment_intent_id=None,
        expires_at=None,
        status=CardHold.Status.SCHEDULED,
        hold_on=timezone.localdate(),
        **fields,
    )


def reload(hold) -> Any:
    hold.refresh_from_db()
    return hold


def creates(fake_stripe) -> list[dict]:
    return [params for _args, params in fake_stripe.calls_to("PaymentIntent.create")]


def unsettled(holder, fake_stripe) -> Any:
    """A due hold whose off-session create got no usable answer: it keeps its key."""
    hold = due(holder)
    fake_stripe.fail_next("PaymentIntent.create", connection_error())
    assert place_scheduled(hold.pk).status == PlacementStatus.IN_PROGRESS
    hold = reload(hold)
    assert hold.placement_key
    return hold


class TestABadKeyIsNoAnswer:
    @pytest.mark.parametrize(
        "error",
        [
            stripe.AuthenticationError("Invalid API Key", http_status=401),
            stripe.PermissionError("This key can't create PaymentIntents", http_status=403),
        ],
    )
    def test_the_hold_stays_scheduled_and_nobody_is_emailed(
        self, holder, fake_stripe, deferral, mailoutbox, caplog, error
    ) -> None:
        """Reviewer's repro: an AuthenticationError failed every due hold for good."""
        grant_card_hold_perm(UserFactory(is_staff=True, email="ops@example.com"))
        hold = due(holder)
        fake_stripe.fail_next("PaymentIntent.create", error)

        with caplog.at_level("ERROR", logger="baseapp_payments.holds"):
            result = place_scheduled(hold.pk)

        assert result.status == PlacementStatus.IN_PROGRESS
        hold = reload(hold)
        assert hold.status == CardHold.Status.SCHEDULED
        assert hold.failure_code == "" and hold.failed_at is None
        assert hold.placement_key and hold.placement_claimed_at is None
        assert mailoutbox == []
        assert any(record.levelname == "ERROR" for record in caplog.records)

        # Once the key is fixed, the same key places it.
        assert place_scheduled(hold.pk).status == PlacementStatus.PLACED
        keys = {params["idempotency_key"] for params in creates(fake_stripe)}
        assert keys == {hold.placement_key}


class TestAnUnsettledPlacementWhoseTargetIsGone:
    def test_the_sweep_replays_it_and_cancels_what_comes_back(
        self, holder, fake_stripe, deferral, django_capture_on_commit_callbacks
    ) -> None:
        """M4: deleting the target nulls the link, and nothing settled the create."""
        hold = unsettled(holder, fake_stripe)
        key, amount = hold.placement_key, hold.placement_amount_cents
        with django_capture_on_commit_callbacks(execute=True):
            hold.target.delete()
        hold = reload(hold)
        assert hold.target_document_id is None
        assert hold.status == CardHold.Status.SCHEDULED

        with django_capture_on_commit_callbacks(execute=True):
            sweep_card_holds()

        hold = reload(hold)
        assert hold.status == CardHold.Status.RELEASED
        assert hold.release_reason == CardHold.ReleaseReason.CANCELLED
        assert hold.placement_key == ""
        assert hold.release_confirmed_at is not None
        replay = creates(fake_stripe)[-1]
        assert (replay["idempotency_key"], replay["amount"]) == (key, amount)
        assert fake_stripe.status_of(hold.stripe_payment_intent_id) == "canceled"

    def test_a_declined_replay_releases_it_and_tells_nobody(
        self, holder, fake_stripe, deferral, mailoutbox, django_capture_on_commit_callbacks
    ) -> None:
        grant_card_hold_perm(UserFactory(is_staff=True, email="ops@example.com"))
        hold = unsettled(holder, fake_stripe)
        with django_capture_on_commit_callbacks(execute=True):
            hold.target.delete()
        fake_stripe.next_outcome = ["card_declined"]

        with django_capture_on_commit_callbacks(execute=True):
            sweep_card_holds()

        hold = reload(hold)
        assert hold.status == CardHold.Status.RELEASED
        assert hold.release_confirmed_at is not None
        assert mailoutbox == []

    def test_still_no_answer_keeps_it_for_the_next_sweep(
        self, holder, fake_stripe, deferral, django_capture_on_commit_callbacks
    ) -> None:
        hold = unsettled(holder, fake_stripe)
        with django_capture_on_commit_callbacks(execute=True):
            hold.target.delete()
        fake_stripe.fail_next("PaymentIntent.create", connection_error())

        sweep_card_holds()

        hold = reload(hold)
        assert hold.status == CardHold.Status.SCHEDULED and hold.placement_key

    def test_an_unlinked_scheduled_hold_with_no_key_is_left_alone(
        self, holder, fake_stripe, deferral
    ) -> None:
        hold = CardHoldFactory(
            customer=holder,
            stripe_payment_intent_id=None,
            status=CardHold.Status.SCHEDULED,
            hold_on=timezone.localdate(),
        )

        assert place_scheduled(hold.pk) is None
        assert fake_stripe.calls == []


class TestDeferralOffStopsPlacement:
    def test_place_scheduled_places_nothing(self, holder, fake_stripe) -> None:
        """m1: a place_card_hold queued before deferral was turned off."""
        hold = due(holder)

        assert place_scheduled(hold.pk) is None

        assert fake_stripe.calls == []
        assert reload(hold).placement_key == ""

    def test_a_card_saved_whose_day_has_come_isnt_placed(self, holder, fake_stripe) -> None:
        hold = due(holder)

        result = _place_if_due(
            PlacementResult(PlacementStatus.SCHEDULED, target=hold.target, hold=hold)
        )

        assert result.status == PlacementStatus.SCHEDULED
        assert fake_stripe.calls == []

    def test_reschedule_does_nothing(self, holder, fake_stripe) -> None:
        """m1: the reschedule task skipped the deferral check ``reschedule()`` makes."""
        hold = due(holder)
        CardHold.objects.filter(pk=hold.pk).update(hold_on=days(30))

        assert reschedule_hold(hold.pk) is None
        reschedule_card_hold.delay(hold.pk)

        assert fake_stripe.calls == []
        assert reload(hold).hold_on == days(30)

    def test_a_placed_hold_isnt_moved_back_either(self, holder, fake_stripe) -> None:
        order = HoldableOrderFactory(user=holder, target_date=days(30))
        hold = CardHoldFactory(target=order)

        assert reschedule_hold(hold.pk) is None
        assert reload(hold).status == CardHold.Status.AUTHORIZED
        assert fake_stripe.calls == []

    def test_the_sweep_still_settles_a_placement_already_sent(
        self, holder, fake_stripe, deferral
    ) -> None:
        """Settling a create with no usable answer isn't a new placement: stopping it
        could strand an authorization Stripe made."""
        hold = unsettled(holder, fake_stripe)

        with override_config(CARD_HOLDS_DEFERRAL_ENABLED=False):
            sweep_card_holds()

        hold = reload(hold)
        assert hold.status == CardHold.Status.AUTHORIZED
        assert len({params["idempotency_key"] for params in creates(fake_stripe)}) == 1

    def test_the_sweep_queues_no_new_placement(self, holder, fake_stripe) -> None:
        hold = due(holder)

        sweep_card_holds()

        assert reload(hold).status == CardHold.Status.SCHEDULED
        assert fake_stripe.calls == []

    def test_releases_still_work(self, holder, fake_stripe) -> None:
        hold = due(holder)
        order = hold.target
        order.status = order.Status.CANCELLED
        order.save()

        assert release(hold.pk) is True
        assert reload(hold).status == CardHold.Status.RELEASED
        assert fake_stripe.calls == []


def released_to_reschedule(holder, reason: str, *, confirmed: bool = True) -> Any:
    """A hold released to go back to ``scheduled``, its date inside the window."""
    order = HoldableOrderFactory(user=holder, target_date=days(2))
    return CardHoldFactory(
        target=order,
        status=CardHold.Status.RELEASED,
        release_reason=reason,
        release_confirmed_at=timezone.now() if confirmed else None,
    )


BACK_TO_SCHEDULED = [CardHold.ReleaseReason.NOT_HOLDABLE, CardHold.ReleaseReason.RESCHEDULED]


class TestDeferralOffStillReturnsToScheduled:
    """The flag stops new placements only: a hold released ``not_holdable`` or
    ``rescheduled`` still goes back to ``scheduled``, where it waits for capture()."""

    @pytest.mark.parametrize("reason", BACK_TO_SCHEDULED)
    def test_the_sweep_puts_it_back_and_places_nothing(self, holder, fake_stripe, reason) -> None:
        hold = released_to_reschedule(holder, reason)
        payment_intent_id = hold.stripe_payment_intent_id

        sweep_card_holds()

        hold = reload(hold)
        assert hold.status == CardHold.Status.SCHEDULED
        assert hold.hold_on == days(-2)  # its day has come, but nothing is placed
        assert hold.previous_payment_intent_ids == [payment_intent_id]
        assert fake_stripe.calls == []

    def test_capture_then_charges_it(self, holder, fake_stripe) -> None:
        hold = released_to_reschedule(holder, CardHold.ReleaseReason.NOT_HOLDABLE)
        sweep_card_holds()
        charge = Mock(return_value="ch_new")

        result = capture(hold.pk, 10_000, charge=charge)

        assert result.status == CaptureStatus.CHARGED
        charge.assert_called_once_with(idempotency_key=charge_idempotency_key(hold.pk))
        assert reload(hold).release_reason == CardHold.ReleaseReason.FOR_CHARGE

    def test_release_for_charge_releases_it_for_its_caller(self, holder, fake_stripe) -> None:
        hold = released_to_reschedule(holder, CardHold.ReleaseReason.NOT_HOLDABLE)
        sweep_card_holds()

        assert release_for_charge(hold.pk) is True

        hold = reload(hold)
        assert hold.status == CardHold.Status.RELEASED
        assert hold.release_reason == CardHold.ReleaseReason.FOR_CHARGE
        charge = Mock()
        assert capture(hold.pk, 10_000, charge=charge).status == CaptureStatus.NOT_CAPTURED
        charge.assert_not_called()

    @pytest.mark.parametrize("reason", BACK_TO_SCHEDULED)
    def test_release_for_charge_before_the_sweep_releases_it_too(
        self, holder, fake_stripe, reason
    ) -> None:
        hold = released_to_reschedule(holder, reason)

        assert release_for_charge(hold.pk) is True
        assert release_for_charge(hold.pk) is True

        hold = reload(hold)
        assert hold.release_reason == CardHold.ReleaseReason.FOR_CHARGE
        sweep_card_holds()
        assert reload(hold).status == CardHold.Status.RELEASED
        assert fake_stripe.calls == []

    def test_release_for_charge_waits_for_stripe_to_confirm_the_cancel(
        self, holder, fake_stripe
    ) -> None:
        hold = released_to_reschedule(holder, CardHold.ReleaseReason.NOT_HOLDABLE, confirmed=False)

        assert release_for_charge(hold.pk) is False
        assert reload(hold).release_reason == CardHold.ReleaseReason.NOT_HOLDABLE

    def test_an_unconfirmed_cancel_is_finished_then_put_back(self, holder, fake_stripe) -> None:
        hold = released_to_reschedule(holder, CardHold.ReleaseReason.RESCHEDULED, confirmed=False)

        result = reschedule_hold(hold.pk)

        assert result.status == PlacementStatus.SCHEDULED
        assert fake_stripe.calls_to("PaymentIntent.cancel")
        assert fake_stripe.calls_to("PaymentIntent.create") == []
        assert reload(hold).status == CardHold.Status.SCHEDULED
