"""Releases Stripe hasn't confirmed: the sweep re-drives them, survives broker errors,
skips work in flight, and records a PaymentIntent found captured as captured (M2, m4)."""

import datetime
from collections.abc import Generator
from typing import Any
from unittest.mock import patch

import pytest
import swapper
from django.utils import timezone
from kombu.exceptions import OperationalError

from baseapp_payments.holds import abandon_hold, release
from baseapp_payments.tasks import release_card_hold, sweep_card_holds
from testproject.testapp.models import HoldableOrder

from ..factories import CardHoldFactory
from ..fakes import connection_error

CardHold = swapper.load_model("baseapp_payments", "CardHold")

pytestmark = pytest.mark.django_db


@pytest.fixture
def eager_retries() -> Generator[None, None, None]:
    """Run Celery's eager retries through to the end instead of raising ``Retry``."""
    conf = release_card_hold._get_app().conf
    keys = ("task_eager_propagates", "CELERY_TASK_EAGER_PROPAGATES")
    before = {key: conf.get(key) for key in keys}
    conf.update({key: False for key in keys})
    yield
    conf.update(before)


def live_hold(fake_stripe: Any, *, status: str = "requires_capture", **fields: Any) -> Any:
    hold = CardHoldFactory(**fields)
    fake_stripe.intents[hold.stripe_payment_intent_id] = {
        "id": hold.stripe_payment_intent_id,
        "object": "payment_intent",
        "status": status,
        "amount": hold.amount_cents,
        "payment_method": "pm_visa",
        "capture_before": None,
        "amount_received": hold.amount_cents if status == "succeeded" else 0,
    }
    return hold


def released_unconfirmed(fake_stripe: Any, holder: Any, **fields: Any) -> Any:
    """An unlinked hold marked released 20 minutes ago whose cancel never reached Stripe."""
    hold = live_hold(fake_stripe, customer=holder, **fields)
    CardHold.objects.filter(pk=hold.pk).update(
        status=CardHold.Status.RELEASED,
        modified=timezone.now() - datetime.timedelta(minutes=20),
    )
    return hold


def broker_down() -> Any:
    return patch.object(
        release_card_hold, "delay", side_effect=OperationalError("broker unreachable")
    )


def refreshed(hold: Any) -> Any:
    hold.refresh_from_db()
    return hold


class TestConfirmation:
    def test_a_confirmed_cancel_records_when(self, order, fake_stripe) -> None:
        order.status = HoldableOrder.Status.CANCELLED
        order.save()
        hold = live_hold(fake_stripe, target=order)

        release_card_hold.delay(hold.pk)

        hold = refreshed(hold)
        assert hold.status == CardHold.Status.RELEASED
        assert hold.release_confirmed_at is not None
        assert hold.release_requested_at is None

    def test_a_payment_intent_stripe_doesnt_know_counts_as_released(
        self, holder, fake_stripe
    ) -> None:
        hold = released_unconfirmed(fake_stripe, holder)
        del fake_stripe.intents[hold.stripe_payment_intent_id]

        assert release(hold.pk, claimed=True) is True
        assert refreshed(hold).release_confirmed_at is not None

    def test_a_payment_intent_found_captured_is_marked_captured_never_released(
        self, order, fake_stripe
    ) -> None:
        order.status = HoldableOrder.Status.CANCELLED
        order.save()
        hold = live_hold(fake_stripe, target=order, status="succeeded")

        release_card_hold.delay(hold.pk)

        hold = refreshed(hold)
        assert hold.status == CardHold.Status.CAPTURED
        assert hold.captured_amount_cents == hold.amount_cents
        assert hold.release_confirmed_at is None


class TestSweepReDrive:
    def test_a_broker_failure_at_commit_is_re_driven_by_the_sweep(
        self, holder, fake_stripe, django_capture_on_commit_callbacks
    ) -> None:
        hold = live_hold(fake_stripe, customer=holder)
        CardHold.objects.filter(pk=hold.pk).update(status=CardHold.Status.PENDING)

        with broker_down(), django_capture_on_commit_callbacks(execute=True):
            abandon_hold(hold.stripe_payment_intent_id)  # its release task never queues

        hold = refreshed(hold)
        assert hold.status == CardHold.Status.RELEASED
        assert hold.release_confirmed_at is None
        assert fake_stripe.status_of(hold.stripe_payment_intent_id) == "requires_capture"

        CardHold.objects.filter(pk=hold.pk).update(
            modified=timezone.now() - datetime.timedelta(minutes=20)
        )
        sweep_card_holds()

        assert fake_stripe.status_of(hold.stripe_payment_intent_id) == "canceled"
        assert refreshed(hold).release_confirmed_at is not None

    def test_exhausted_retries_are_re_driven_by_the_sweep(
        self, holder, fake_stripe, eager_retries, caplog
    ) -> None:
        hold = released_unconfirmed(fake_stripe, holder)
        for _ in range(13):
            fake_stripe.fail_next("PaymentIntent.cancel", connection_error())

        release_card_hold.apply(
            args=[hold.pk],
            kwargs={"claimed": True, "payment_intent_id": hold.stripe_payment_intent_id},
            throw=False,
        )

        assert "Gave up releasing card hold" in caplog.text
        hold = refreshed(hold)
        assert hold.release_confirmed_at is None
        assert hold.release_requested_at is None  # cleared, so the sweep may retry

        CardHold.objects.filter(pk=hold.pk).update(
            modified=timezone.now() - datetime.timedelta(minutes=20)
        )
        sweep_card_holds()

        assert fake_stripe.status_of(hold.stripe_payment_intent_id) == "canceled"
        assert refreshed(hold).release_confirmed_at is not None

    def test_an_expired_unconfirmed_hold_is_left_to_lapse(self, holder, fake_stripe) -> None:
        hold = released_unconfirmed(
            fake_stripe, holder, expires_at=timezone.now() - datetime.timedelta(minutes=1)
        )

        sweep_card_holds()

        assert fake_stripe.calls_to("PaymentIntent.cancel") == []
        assert refreshed(hold).release_confirmed_at is None

    def test_releasing_an_expired_hold_still_asks_stripe(self, holder, fake_stripe) -> None:
        """M1: past its expiry the authorization may still be live: it is cancelled."""
        hold = released_unconfirmed(
            fake_stripe, holder, expires_at=timezone.now() - datetime.timedelta(minutes=1)
        )

        assert release(hold.pk, claimed=True) is True

        assert fake_stripe.status_of(hold.stripe_payment_intent_id) == "canceled"
        assert refreshed(hold).release_confirmed_at is not None

    def test_a_just_released_hold_waits_for_its_own_task(self, holder, fake_stripe) -> None:
        hold = live_hold(fake_stripe, customer=holder)
        CardHold.objects.filter(pk=hold.pk).update(status=CardHold.Status.RELEASED)

        sweep_card_holds()

        assert fake_stripe.calls_to("PaymentIntent.cancel") == []

    def test_a_release_in_flight_is_not_queued_again(self, holder, fake_stripe) -> None:
        busy = released_unconfirmed(fake_stripe, holder)
        stale = released_unconfirmed(fake_stripe, holder)
        CardHold.objects.filter(pk=busy.pk).update(release_requested_at=timezone.now())
        CardHold.objects.filter(pk=stale.pk).update(
            release_requested_at=timezone.now() - datetime.timedelta(hours=1)
        )

        with patch.object(release_card_hold, "delay") as delay:
            sweep_card_holds()

        assert [call.args[0] for call in delay.call_args_list] == [stale.pk]

    def test_open_holds_in_flight_are_skipped_too(self, order, fake_stripe) -> None:
        order.status = HoldableOrder.Status.CANCELLED
        order.save()
        hold = live_hold(fake_stripe, target=order)
        CardHold.objects.filter(pk=hold.pk).update(release_requested_at=timezone.now())

        with patch.object(release_card_hold, "delay") as delay:
            sweep_card_holds()

        delay.assert_not_called()

    def test_one_broker_failure_doesnt_stop_the_sweep(self, holder, fake_stripe) -> None:
        old = timezone.now() - datetime.timedelta(hours=1)
        first = live_hold(fake_stripe, customer=holder)
        second = live_hold(fake_stripe, customer=holder)
        CardHold.objects.filter(pk__in=[first.pk, second.pk]).update(
            status=CardHold.Status.PENDING, created=old
        )
        queued = []

        def delay(card_hold_id: int, **kwargs: Any) -> None:
            if not queued:
                queued.append(None)
                raise OperationalError("broker unreachable")
            queued.append(card_hold_id)

        with patch.object(release_card_hold, "delay", side_effect=delay):
            sweep_card_holds()

        # Both were claimed; the one that failed to queue is released but unconfirmed,
        # and the next sweep picks it up.
        assert len(queued) == 2
        assert {refreshed(first).status, refreshed(second).status} == {CardHold.Status.RELEASED}
        CardHold.objects.filter(pk__in=[first.pk, second.pk]).update(modified=old)
        sweep_card_holds()
        assert refreshed(first).release_confirmed_at is not None
        assert refreshed(second).release_confirmed_at is not None


class TestInFlightStamp:
    def test_the_task_stamps_while_retrying_and_clears_when_done(self, holder, fake_stripe) -> None:
        hold = released_unconfirmed(fake_stripe, holder)
        stamps = []
        original = fake_stripe.PaymentIntent.cancel

        def cancel(payment_intent_id: str, **params: Any) -> Any:
            stamps.append(refreshed(hold).release_requested_at)
            return original(payment_intent_id, **params)

        with patch.object(fake_stripe.PaymentIntent, "cancel", side_effect=cancel):
            release_card_hold.delay(
                hold.pk, claimed=True, payment_intent_id=hold.stripe_payment_intent_id
            )

        assert stamps[0] is not None
        assert refreshed(hold).release_requested_at is None

    def test_an_unexpected_error_clears_the_stamp(self, holder, fake_stripe) -> None:
        hold = released_unconfirmed(fake_stripe, holder)

        with (
            patch("baseapp_payments.holds.release", side_effect=RuntimeError("boom")),
            pytest.raises(RuntimeError),
        ):
            release_card_hold.delay(hold.pk, claimed=True)

        assert refreshed(hold).release_requested_at is None
