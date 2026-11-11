"""Releasing card holds: the release task, the sweep, and deleting a target."""

import datetime
import logging
from collections.abc import Generator
from typing import Any
from unittest.mock import patch

import pytest
import swapper
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone

from baseapp_core.models import DocumentId
from baseapp_payments import holds, tasks
from baseapp_payments.holds import (
    claim_orphan,
    mark_released,
    release,
    release_for_charge,
    release_target_holds_on_commit,
)
from baseapp_payments.tasks import (
    backoff_countdown,
    release_card_hold,
    sweep_card_holds,
)
from testproject.testapp.models import HoldableOrder

from ..factories import CardHoldFactory, HoldableOrderFactory
from ..fakes import api_error, connection_error, unexpected_state

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


def live_hold(fake_stripe, *, status="requires_capture", **fields) -> Any:
    """A hold whose PaymentIntent exists in the fake Stripe."""
    hold = CardHoldFactory(**fields)
    fake_stripe.intents[hold.stripe_payment_intent_id] = {
        "id": hold.stripe_payment_intent_id,
        "object": "payment_intent",
        "status": status,
        "amount": hold.amount_cents,
        "payment_method": "pm_visa",
        "capture_before": None,
    }
    return hold


def cancelled(order: HoldableOrder) -> HoldableOrder:
    order.status = HoldableOrder.Status.CANCELLED
    order.save()
    return order


def releases_queued(callbacks) -> int:
    return sum("release_on_commit" in callback.__qualname__ for callback in callbacks)


def status_of(hold) -> str:
    hold.refresh_from_db()
    return hold.status


class TestRelease:
    def test_a_cancelled_target_is_released(self, order, fake_stripe) -> None:
        hold = live_hold(fake_stripe, target=cancelled(order))

        release_card_hold.delay(hold.pk)

        assert status_of(hold) == CardHold.Status.RELEASED
        assert fake_stripe.status_of(hold.stripe_payment_intent_id) == "canceled"

    def test_an_active_target_is_never_released(self, order, fake_stripe, caplog) -> None:
        caplog.set_level(logging.INFO)
        hold = live_hold(fake_stripe, target=order)

        release_card_hold.delay(hold.pk)

        assert status_of(hold) == CardHold.Status.AUTHORIZED
        assert fake_stripe.calls_to("PaymentIntent.cancel") == []
        assert "backs an active target" in caplog.text

    def test_a_hold_a_live_capture_claims_is_left_to_it(self, order, fake_stripe) -> None:
        """#6: release() ignored the capture claim; the sweep retries it later."""
        hold = live_hold(fake_stripe, target=cancelled(order))
        CardHold.objects.filter(pk=hold.pk).update(capture_claimed_at=timezone.now())

        release_card_hold.delay(hold.pk)

        assert status_of(hold) == CardHold.Status.AUTHORIZED
        assert fake_stripe.calls_to("PaymentIntent.cancel") == []

        CardHold.objects.filter(pk=hold.pk).update(
            capture_claimed_at=timezone.now()
            - holds.CAPTURE_CLAIM_TIMEOUT
            - datetime.timedelta(seconds=1)
        )
        release_card_hold.delay(hold.pk)
        assert status_of(hold) == CardHold.Status.RELEASED

    # A scheduled hold is released too, with no Stripe call (test_card_hold_deferral).
    @pytest.mark.parametrize("closed", ["released", "captured", "failed"])
    def test_only_open_holds_are_released(self, order, fake_stripe, closed) -> None:
        hold = live_hold(fake_stripe, target=cancelled(order))
        CardHold.objects.filter(pk=hold.pk).update(status=closed)

        release_card_hold.delay(hold.pk)

        assert status_of(hold) == closed
        assert fake_stripe.calls_to("PaymentIntent.cancel") == []

    @pytest.mark.parametrize("lapsed_in_stripe", [False, True])
    def test_an_expired_hold_is_cancelled_or_confirmed_through_stripe(
        self, order, fake_stripe, lapsed_in_stripe
    ) -> None:
        """M1: Stripe is asked even past the expiry. Still held: cancelled. Cancelled
        by Stripe when it lapsed: confirmed."""
        hold = live_hold(
            fake_stripe,
            target=cancelled(order),
            expires_at=timezone.now() - datetime.timedelta(minutes=1),
        )
        if lapsed_in_stripe:
            fake_stripe.lapse(hold.stripe_payment_intent_id)

        release_card_hold.delay(hold.pk)

        hold.refresh_from_db()
        assert hold.status == CardHold.Status.RELEASED
        assert hold.release_reason == CardHold.ReleaseReason.CANCELLED
        assert hold.release_confirmed_at is not None
        assert len(fake_stripe.calls_to("PaymentIntent.cancel")) == 1
        assert fake_stripe.status_of(hold.stripe_payment_intent_id) == "canceled"

    def test_an_expired_hold_found_captured_is_recorded_with_its_amount(
        self, order, fake_stripe
    ) -> None:
        hold = live_hold(
            fake_stripe,
            target=cancelled(order),
            status="succeeded",
            expires_at=timezone.now() - datetime.timedelta(minutes=1),
        )
        fake_stripe.intents[hold.stripe_payment_intent_id]["amount_received"] = 10_500

        assert release(hold.pk) is False

        hold.refresh_from_db()
        assert hold.status == CardHold.Status.CAPTURED
        assert hold.captured_amount_cents == 10_500

    def test_the_release_reason_is_recorded(self, order, holder, fake_stripe) -> None:
        charged = HoldableOrderFactory(user=holder, status=HoldableOrder.Status.CHARGED)
        done = live_hold(fake_stripe, target=charged)
        orphan = live_hold(fake_stripe, customer=holder, status="requires_capture")
        CardHold.objects.filter(pk=orphan.pk).update(status=CardHold.Status.PENDING)

        assert release(done.pk, card_released=True) is True
        assert release(orphan.pk) is True

        done.refresh_from_db()
        orphan.refresh_from_db()
        assert done.release_reason == CardHold.ReleaseReason.CARD_RELEASED
        assert orphan.release_reason == CardHold.ReleaseReason.ABANDONED

    def test_an_already_canceled_payment_intent_counts_as_released(
        self, order, fake_stripe
    ) -> None:
        hold = live_hold(fake_stripe, target=cancelled(order), status="canceled")

        release_card_hold.delay(hold.pk)

        assert status_of(hold) == CardHold.Status.RELEASED

    def test_an_already_canceled_state_is_read_from_stripe_when_missing(
        self, order, fake_stripe
    ) -> None:
        hold = live_hold(fake_stripe, target=cancelled(order), status="canceled")
        fake_stripe.fail_next(
            "PaymentIntent.cancel",
            unexpected_state(hold.stripe_payment_intent_id, "?", "cancel", with_intent=False),
        )

        release_card_hold.delay(hold.pk)

        assert status_of(hold) == CardHold.Status.RELEASED
        assert fake_stripe.calls_to("PaymentIntent.retrieve")

    def test_another_refusal_is_logged_and_the_hold_kept(self, order, fake_stripe, caplog) -> None:
        hold = live_hold(fake_stripe, target=cancelled(order), status="processing")
        fake_stripe.fail_next(
            "PaymentIntent.cancel",
            unexpected_state(hold.stripe_payment_intent_id, "processing", "cancel"),
        )

        release_card_hold.delay(hold.pk)

        assert status_of(hold) == CardHold.Status.AUTHORIZED
        assert "Stripe refused to cancel PaymentIntent" in caplog.text

    def test_a_retry_that_succeeds_releases(self, order, fake_stripe, eager_retries) -> None:
        hold = live_hold(fake_stripe, target=cancelled(order))
        fake_stripe.fail_next("PaymentIntent.cancel", connection_error())
        fake_stripe.fail_next("PaymentIntent.cancel", api_error())

        release_card_hold.apply(args=[hold.pk], throw=False)

        assert status_of(hold) == CardHold.Status.RELEASED
        assert len(fake_stripe.calls_to("PaymentIntent.cancel")) == 3

    def test_retries_are_bounded_at_twelve(self, order, fake_stripe, caplog, eager_retries) -> None:
        hold = live_hold(fake_stripe, target=cancelled(order))
        for _ in range(20):
            fake_stripe.fail_next("PaymentIntent.cancel", connection_error())

        release_card_hold.apply(args=[hold.pk], throw=False)

        assert len(fake_stripe.calls_to("PaymentIntent.cancel")) == 13  # 1 + 12 retries
        assert status_of(hold) == CardHold.Status.AUTHORIZED
        assert "Gave up releasing card hold" in caplog.text

    def test_the_backoff_is_capped_at_1500_seconds(self) -> None:
        assert [backoff_countdown(n) for n in range(6)] == [60, 120, 240, 480, 960, 1500]
        assert backoff_countdown(12) == 1500

    def test_an_unlinked_pending_hold_is_claimed_before_the_cancel(
        self, holder, fake_stripe
    ) -> None:
        hold = live_hold(fake_stripe, customer=holder)
        CardHold.objects.filter(pk=hold.pk).update(status=CardHold.Status.PENDING)

        assert release(hold.pk) is True

        assert status_of(hold) == CardHold.Status.RELEASED
        assert fake_stripe.status_of(hold.stripe_payment_intent_id) == "canceled"

    def test_a_deleted_target_without_document_row_counts_as_cancelled(
        self, order, fake_stripe
    ) -> None:
        hold = live_hold(fake_stripe, customer=order.user)
        # A DocumentId that outlived its object (a target without DocumentIdMixin).
        CardHold.objects.filter(pk=hold.pk).update(
            target_document=DocumentId.objects.create(
                content_type=ContentType.objects.get_for_model(HoldableOrder),
                object_id=order.pk + 10_000,
            )
        )

        assert release(hold.pk) is True
        assert status_of(hold) == CardHold.Status.RELEASED

    def test_a_hold_on_an_unregistered_target_is_left_alone(
        self, holder, fake_stripe, caplog
    ) -> None:
        hold = live_hold(fake_stripe, customer=holder)
        CardHold.objects.filter(pk=hold.pk).update(
            target_document=DocumentId.get_or_create_for_object(holder)
        )

        assert release(hold.pk) is False
        assert "unregistered target" in caplog.text

    def test_a_hold_relinked_while_claiming_is_left_for_later(
        self, order, fake_stripe, caplog
    ) -> None:
        caplog.set_level(logging.INFO)
        hold = live_hold(fake_stripe, customer=order.user)
        CardHold.objects.filter(pk=hold.pk).update(status=CardHold.Status.PENDING)
        document = DocumentId.get_or_create_for_object(order)
        manager = type(CardHold.objects)
        original = manager.select_for_update

        def linked_meanwhile(self, *args, **kwargs) -> Any:
            CardHold.objects.filter(pk=hold.pk).update(target_document=document)
            return original(self, *args, **kwargs)

        with patch.object(manager, "select_for_update", linked_meanwhile):
            assert release(hold.pk) is False

        assert status_of(hold) == CardHold.Status.PENDING
        assert "changed target meanwhile" in caplog.text

    def test_mark_released_only_changes_open_holds(self, order) -> None:
        hold = CardHoldFactory(target=order, status=CardHold.Status.CAPTURED)
        assert mark_released(hold.pk) is False

    def test_release_target_holds_on_commit(
        self, order, fake_stripe, django_capture_on_commit_callbacks
    ) -> None:
        hold = live_hold(fake_stripe, target=order)
        cancelled(order)

        with django_capture_on_commit_callbacks(execute=True) as callbacks:
            release_target_holds_on_commit(order)

        assert releases_queued(callbacks) == 1
        assert status_of(hold) == CardHold.Status.RELEASED
        assert holds.open_hold_ids_for(HoldableOrder(user=order.user)) == []


class TestReleaseForCharge:
    def test_releases_an_active_targets_hold(self, order, fake_stripe) -> None:
        hold = live_hold(fake_stripe, target=order)

        assert release_for_charge(hold.pk) is True

        assert status_of(hold) == CardHold.Status.RELEASED
        assert fake_stripe.status_of(hold.stripe_payment_intent_id) == "canceled"

    def test_an_expired_hold_still_held_is_cancelled_first(self, order, fake_stripe) -> None:
        """M2: Stripe still reads requires_capture: cancel, and only then say released."""
        hold = live_hold(
            fake_stripe, target=order, expires_at=timezone.now() - datetime.timedelta(seconds=1)
        )

        assert release_for_charge(hold.pk) is True
        assert fake_stripe.status_of(hold.stripe_payment_intent_id) == "canceled"
        hold.refresh_from_db()
        assert hold.status == CardHold.Status.RELEASED
        assert hold.release_reason == CardHold.ReleaseReason.FOR_CHARGE

    def test_an_expired_hold_whose_cancel_fails_is_not_released(self, order, fake_stripe) -> None:
        hold = live_hold(
            fake_stripe, target=order, expires_at=timezone.now() - datetime.timedelta(seconds=1)
        )
        fake_stripe.fail_next(
            "PaymentIntent.cancel",
            unexpected_state(hold.stripe_payment_intent_id, "processing", "cancel"),
        )

        assert release_for_charge(hold.pk) is False
        assert status_of(hold) == CardHold.Status.AUTHORIZED

    def test_a_closed_hold_is_untouched(self, order, fake_stripe) -> None:
        hold = live_hold(fake_stripe, target=order, status="succeeded")
        CardHold.objects.filter(pk=hold.pk).update(status=CardHold.Status.CAPTURED)

        assert release_for_charge(hold.pk) is False
        assert fake_stripe.calls == []

    def test_a_refusal_leaves_the_hold_to_lapse(self, order, fake_stripe) -> None:
        hold = live_hold(fake_stripe, target=order, status="processing")
        fake_stripe.fail_next(
            "PaymentIntent.cancel",
            unexpected_state(hold.stripe_payment_intent_id, "processing", "cancel"),
        )

        assert release_for_charge(hold.pk) is False
        assert status_of(hold) == CardHold.Status.AUTHORIZED

    def test_a_payment_intent_found_captured_is_recorded_captured(self, order, fake_stripe) -> None:
        hold = live_hold(fake_stripe, target=order, status="succeeded")

        assert release_for_charge(hold.pk) is False
        assert status_of(hold) == CardHold.Status.CAPTURED

    def test_transient_errors_propagate(self, order, fake_stripe) -> None:
        hold = live_hold(fake_stripe, target=order)
        fake_stripe.fail_next("PaymentIntent.cancel", connection_error())

        with pytest.raises(Exception):
            release_for_charge(hold.pk)


class TestSweep:
    def old(self, hold, minutes=31) -> Any:
        CardHold.objects.filter(pk=hold.pk).update(
            created=timezone.now() - datetime.timedelta(minutes=minutes)
        )
        return hold

    def test_orphans_are_claimed_and_released(self, holder, fake_stripe) -> None:
        orphan = self.old(live_hold(fake_stripe, customer=holder))
        CardHold.objects.filter(pk=orphan.pk).update(status=CardHold.Status.PENDING)
        recent = live_hold(fake_stripe, customer=holder)

        sweep_card_holds()

        assert status_of(orphan) == CardHold.Status.RELEASED
        assert fake_stripe.status_of(orphan.stripe_payment_intent_id) == "canceled"
        assert status_of(recent) == CardHold.Status.AUTHORIZED

    def test_an_orphan_linked_since_the_listing_is_skipped(self, order) -> None:
        hold = CardHoldFactory(customer=order.user, status=CardHold.Status.PENDING)
        CardHold.objects.filter(pk=hold.pk).update(
            target_document=DocumentId.get_or_create_for_object(order)
        )

        assert claim_orphan(hold.pk) is False

    def test_holds_on_cancelled_targets_are_released(self, holder, fake_stripe) -> None:
        on_cancelled = live_hold(fake_stripe, target=cancelled(HoldableOrderFactory(user=holder)))
        on_open = live_hold(fake_stripe, target=HoldableOrderFactory(user=holder))

        sweep_card_holds()

        assert status_of(on_cancelled) == CardHold.Status.RELEASED
        assert status_of(on_open) == CardHold.Status.AUTHORIZED

    def test_holds_on_card_released_targets_are_released(self, holder, fake_stripe) -> None:
        charged = HoldableOrderFactory(user=holder, status=HoldableOrder.Status.CHARGED)
        in_flight = HoldableOrderFactory(
            user=holder, status=HoldableOrder.Status.CHARGED, charge_in_flight=True
        )
        released = live_hold(fake_stripe, target=charged)
        kept = live_hold(fake_stripe, target=in_flight)

        sweep_card_holds()

        assert status_of(released) == CardHold.Status.RELEASED
        assert status_of(kept) == CardHold.Status.AUTHORIZED

    def test_a_charge_that_starts_before_the_release_runs_keeps_the_hold(
        self, holder, fake_stripe
    ) -> None:
        charged = HoldableOrderFactory(user=holder, status=HoldableOrder.Status.CHARGED)
        hold = live_hold(fake_stripe, target=charged)
        HoldableOrder.objects.filter(pk=charged.pk).update(charge_in_flight=True)

        # Re-checked under the lock: the release task refuses.
        release_card_hold.delay(hold.pk, card_released=True)

        assert status_of(hold) == CardHold.Status.AUTHORIZED

    def test_the_card_released_path_needs_the_flag(self, holder, fake_stripe) -> None:
        charged = HoldableOrderFactory(user=holder, status=HoldableOrder.Status.CHARGED)
        hold = live_hold(fake_stripe, target=charged)

        release_card_hold.delay(hold.pk)

        assert status_of(hold) == CardHold.Status.AUTHORIZED

    def test_the_beat_entry_runs_every_15_minutes(self) -> None:
        from baseapp_core.plugins import plugin_registry

        entry = plugin_registry.get_all_celery_schedules()["baseapp_payments_card_holds_sweep"]
        assert entry["task"] == "baseapp_payments.tasks.sweep_card_holds"
        assert entry["schedule"] == 15 * 60
        assert entry["options"] == {"expires": 15 * 60}
        assert sweep_card_holds.name == entry["task"]


class TestNoStripeKey:
    def test_every_task_is_a_no_op(self, order, fake_stripe, settings) -> None:
        settings.STRIPE_SECRET_KEY = ""
        hold = live_hold(fake_stripe, target=cancelled(order))
        self_orphan = CardHoldFactory(customer=order.user, status=CardHold.Status.PENDING)
        CardHold.objects.filter(pk=self_orphan.pk).update(
            created=timezone.now() - datetime.timedelta(hours=1)
        )

        release_card_hold.delay(hold.pk)
        sweep_card_holds()

        assert release(hold.pk) is False
        assert status_of(hold) == CardHold.Status.AUTHORIZED
        assert status_of(self_orphan) == CardHold.Status.PENDING
        assert fake_stripe.calls == []

    def test_without_a_card_hold_model_tasks_do_nothing(
        self, order, fake_stripe, django_assert_num_queries
    ) -> None:
        """N7: the beat entry is registered at settings import, before the project's
        BASEAPP_PAYMENTS_CARDHOLD_MODEL is readable, so the sweep itself is the gate: it
        returns before any query or Stripe call."""
        hold = live_hold(fake_stripe, target=cancelled(order))
        with (
            patch.object(tasks, "card_holds_enabled", return_value=False),
            django_assert_num_queries(0),
        ):
            release_card_hold.delay(hold.pk)
            sweep_card_holds()
        assert fake_stripe.calls == []


class TestDeletingATarget:
    def test_its_open_holds_are_released_through_the_document_cascade(
        self, order, fake_stripe, django_capture_on_commit_callbacks
    ) -> None:
        hold = live_hold(fake_stripe, target=order)
        document_id = hold.target_document_id

        with django_capture_on_commit_callbacks(execute=True) as callbacks:
            order.delete()

        # The GenericRelation cascade deleted the DocumentId and nulled the link...
        assert not DocumentId.objects.filter(pk=document_id).exists()
        hold.refresh_from_db()
        assert hold.target_document_id is None
        # ...after the pre_delete receiver read the hold, so it was released.
        assert releases_queued(callbacks) == 1
        assert hold.status == CardHold.Status.RELEASED
        assert fake_stripe.status_of(hold.stripe_payment_intent_id) == "canceled"

    def test_closed_holds_queue_nothing(
        self, order, fake_stripe, django_capture_on_commit_callbacks
    ) -> None:
        hold = live_hold(fake_stripe, target=order)
        CardHold.objects.filter(pk=hold.pk).update(status=CardHold.Status.CAPTURED)

        with django_capture_on_commit_callbacks(execute=True) as callbacks:
            order.delete()

        assert callbacks == []
        assert fake_stripe.calls == []

    def test_deleting_through_a_proxy_releases_the_holds_too(
        self, order, fake_stripe, django_capture_on_commit_callbacks
    ) -> None:
        """m3: Django sends ``pre_delete`` with the proxy class, so a receiver connected
        to the concrete model alone missed the delete."""
        from baseapp_payments.signals import connect_target_receivers

        from ..helpers import holdable_order_proxy

        proxy = holdable_order_proxy()
        connect_target_receivers()
        hold = live_hold(fake_stripe, target=order)

        with django_capture_on_commit_callbacks(execute=True):
            proxy.objects.get(pk=order.pk).delete()

        hold.refresh_from_db()
        assert hold.status == CardHold.Status.RELEASED
        assert fake_stripe.status_of(hold.stripe_payment_intent_id) == "canceled"

    def test_the_receiver_is_connected_per_registered_model(self) -> None:
        from django.db.models.signals import pre_delete

        assert pre_delete.has_listeners(HoldableOrder)
        assert "testapp.HoldableOrder" in settings.BASEAPP_PAYMENTS_CARD_HOLD_TARGETS
