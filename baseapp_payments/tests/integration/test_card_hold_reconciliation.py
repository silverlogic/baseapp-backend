"""Reconciling card holds with Stripe when a create got no usable answer (review #2).

A 5xx may hide an authorization Stripe made. Stripe replays the key's answer for 24
hours at least, then may forget the key, and a replay runs as a fresh request: a second
authorization. So holds are reconciled by ``metadata['card_hold_id']``: from Stripe's
webhook (primary), and by a lookup once the key is 23 hours old (backup). Stripe is the
in-memory ``FakeStripe``; webhook events are signed and posted to the real endpoint.
"""

import datetime
import uuid
from collections.abc import Generator
from typing import Any
from unittest.mock import patch

import pytest
import stripe
import swapper
from constance.test import override_config
from django.test import override_settings
from django.utils import timezone

from baseapp_payments import holds, tasks
from baseapp_payments.holds import (
    PLACEMENT_KEY_TTL,
    PlacementStatus,
    authorize_on_session,
    find_hold_payment_intents,
    place_scheduled,
    reconcile_payment_intent,
    reconcile_stale_send,
)
from baseapp_payments.tasks import reconcile_card_hold, sweep_card_holds
from baseapp_payments.utils import StripeWebhookHandler
from testproject.testapp.card_holds import HoldableOrderHoldTarget
from testproject.testapp.models import HoldableOrder

from ..factories import CardHoldFactory, HoldableOrderFactory
from ..fakes import (
    STRIPE_CUSTOMER_ID,
    WEBHOOK_SECRET,
    api_error,
    connection_error,
    deliver_event,
)

CardHold = swapper.load_model("baseapp_payments", "CardHold")

pytestmark = pytest.mark.django_db

AUTHORIZED = "payment_intent.amount_capturable_updated"
CANCELED = "payment_intent.canceled"
SUCCEEDED = "payment_intent.succeeded"
FAILED = "payment_intent.payment_failed"


@pytest.fixture(autouse=True)
def webhook_secret() -> Generator[None, None, None]:
    with override_settings(STRIPE_WEBHOOK_SECRET=WEBHOOK_SECRET):
        yield


@pytest.fixture
def deferral() -> Generator[None, None, None]:
    with override_config(CARD_HOLDS_DEFERRAL_ENABLED=True):
        yield


@pytest.fixture
def eager_retries() -> Generator[None, None, None]:
    """Run Celery's eager retries through to the end instead of raising ``Retry``."""
    conf = reconcile_card_hold._get_app().conf
    keys = ("task_eager_propagates", "CELERY_TASK_EAGER_PROPAGATES")
    before = {key: conf.get(key) for key in keys}
    conf.update({key: False for key in keys})
    yield
    conf.update(before)


def due(holder, **fields) -> Any:
    """A scheduled hold whose day is today."""
    today = timezone.localdate()
    order = HoldableOrderFactory(user=holder, target_date=today + datetime.timedelta(days=4))
    fields.setdefault("status", CardHold.Status.SCHEDULED)
    return CardHoldFactory(
        target=order, stripe_payment_intent_id=None, expires_at=None, hold_on=today, **fields
    )


def reload(hold) -> Any:
    hold.refresh_from_db()
    return hold


def creates(fake_stripe) -> list[dict]:
    return [params for _args, params in fake_stripe.calls_to("PaymentIntent.create")]


def age(hold, by: datetime.timedelta = PLACEMENT_KEY_TTL + datetime.timedelta(hours=1)) -> None:
    """Pretend the hold's create was first sent ``by`` ago."""
    CardHold.objects.filter(pk=hold.pk).update(placement_sent_at=timezone.now() - by)


def deliver(client, fake_stripe, event_type: str, payment_intent_id: str, capture) -> Any:
    with capture(execute=True):
        response = deliver_event(client, fake_stripe.event(event_type, payment_intent_id))
    assert response.status_code == 200
    return response


def lost_placement(holder, fake_stripe) -> tuple[Any, str]:
    """A due hold whose off-session create authorized behind a 5xx: Stripe made the
    PaymentIntent, the sweep only saw the error."""
    hold = due(holder)
    fake_stripe.fail_behind_next()
    assert place_scheduled(hold.pk).status == PlacementStatus.IN_PROGRESS
    (payment_intent_id,) = fake_stripe.intents
    hold = reload(hold)
    assert hold.status == CardHold.Status.SCHEDULED and hold.placement_key
    assert fake_stripe.intents[payment_intent_id]["metadata"]["card_hold_id"] == str(hold.pk)
    return hold, payment_intent_id


def first_pass(holder, order, attempt_id) -> Any:
    def link(hold) -> HoldableOrder:
        order.save()
        return order

    return authorize_on_session(
        user=holder,
        attempt_id=attempt_id,
        payment_method_id="pm_visa",
        stripe_customer_id=STRIPE_CUSTOMER_ID,
        target=order,
        link=link if order.pk is None else None,
        expected_amount_cents=order.amount_cents,
    )


def new_order(holder) -> HoldableOrder:
    return HoldableOrderFactory.build(user=holder)


class TestTheReviewersScenario:
    """A 5xx at placement that authorized, then the key expires: never two live
    authorizations, and the first one is the one recorded."""

    def test_the_webhook_records_the_authorization_and_a_late_sweep_adds_none(
        self, holder, fake_stripe, deferral, client, django_capture_on_commit_callbacks
    ) -> None:
        hold, payment_intent_id = lost_placement(holder, fake_stripe)

        deliver(
            client, fake_stripe, AUTHORIZED, payment_intent_id, django_capture_on_commit_callbacks
        )

        hold = reload(hold)
        assert hold.status == CardHold.Status.AUTHORIZED
        assert hold.stripe_payment_intent_id == payment_intent_id
        assert hold.placement_key == "" and hold.placement_sent_at is None
        fake_stripe.prune_keys()
        sweep_card_holds()
        assert len(creates(fake_stripe)) == 1
        assert fake_stripe.live_authorizations() == [payment_intent_id]

    def test_without_a_webhook_the_lookup_finds_it_after_23_hours(
        self, holder, fake_stripe, deferral
    ) -> None:
        hold, payment_intent_id = lost_placement(holder, fake_stripe)
        # Within 23 hours the sweep replays the key: Stripe answers the saved 5xx.
        sweep_card_holds()
        assert len(creates(fake_stripe)) == 2 and reload(hold).placement_key
        age(hold)
        fake_stripe.prune_keys()

        sweep_card_holds()

        assert len(creates(fake_stripe)) == 2  # never replayed blind
        (search,) = fake_stripe.calls_to("PaymentIntent.search")
        assert search[1]["query"] == f"metadata['card_hold_id']:'{hold.pk}'"
        hold = reload(hold)
        assert hold.status == CardHold.Status.AUTHORIZED
        assert hold.stripe_payment_intent_id == payment_intent_id
        assert fake_stripe.live_authorizations() == [payment_intent_id]

    def test_the_first_send_time_survives_replays_and_resets_with_the_key(
        self, holder, fake_stripe, deferral
    ) -> None:
        hold = due(holder)
        fake_stripe.fail_next("PaymentIntent.create", api_error())
        place_scheduled(hold.pk)
        sent_at = reload(hold).placement_sent_at
        assert sent_at is not None

        place_scheduled(hold.pk)  # the replay answers the saved 5xx

        assert reload(hold).placement_sent_at == sent_at
        fake_stripe.prune_keys()
        assert place_scheduled(hold.pk).status == PlacementStatus.PLACED
        assert reload(hold).placement_sent_at is None


class TestWebhookOrder:
    def test_a_webhook_before_the_off_session_answer_is_recorded(
        self, holder, fake_stripe, deferral, client, django_capture_on_commit_callbacks
    ) -> None:
        hold = due(holder)
        real = holds._create_off_session

        def webhook_first(claimed) -> tuple:
            payment_intent, error = real(claimed)
            deliver(
                client,
                fake_stripe,
                AUTHORIZED,
                holds.stripe_id(payment_intent),
                django_capture_on_commit_callbacks,
            )
            return payment_intent, error

        with patch.object(holds, "_create_off_session", side_effect=webhook_first):
            result = place_scheduled(hold.pk)

        # The webhook recorded it; the placement's own answer finds nothing left to do.
        assert result.status == PlacementStatus.IN_PROGRESS
        (payment_intent_id,) = fake_stripe.intents
        hold = reload(hold)
        assert hold.status == CardHold.Status.AUTHORIZED
        assert hold.stripe_payment_intent_id == payment_intent_id

    def test_a_webhook_before_the_on_session_answer_is_recorded(
        self, holder, fake_stripe, client, django_capture_on_commit_callbacks
    ) -> None:
        order = new_order(holder)
        real = holds.create_hold_payment_intent

        def webhook_first(**params) -> Any:
            payment_intent = real(**params)
            deliver(
                client,
                fake_stripe,
                AUTHORIZED,
                payment_intent.id,
                django_capture_on_commit_callbacks,
            )
            assert CardHold.objects.get().stripe_payment_intent_id == payment_intent.id
            return payment_intent

        with patch.object(holds, "create_hold_payment_intent", side_effect=webhook_first):
            result = first_pass(holder, order, uuid.uuid4())

        assert result.status == PlacementStatus.PLACED
        hold = CardHold.objects.get()
        assert hold.status == CardHold.Status.AUTHORIZED and hold.target == order
        assert hold.placement_key == ""

    def test_an_on_session_authorization_behind_a_5xx_is_picked_up_by_the_retry(
        self, holder, fake_stripe, client, django_capture_on_commit_callbacks
    ) -> None:
        """The webhook records it on the attempt's row; the retry reads it instead of
        sending the key again (Stripe would answer the saved 5xx, then forget the key)."""
        attempt_id = uuid.uuid4()
        fake_stripe.fail_behind_next()
        assert first_pass(holder, new_order(holder), attempt_id).status == (
            PlacementStatus.IN_PROGRESS
        )
        (payment_intent_id,) = fake_stripe.intents
        deliver(
            client, fake_stripe, AUTHORIZED, payment_intent_id, django_capture_on_commit_callbacks
        )
        fake_stripe.prune_keys()
        sent = len(creates(fake_stripe))

        result = first_pass(holder, new_order(holder), attempt_id)

        assert result.status == PlacementStatus.PLACED
        assert len(creates(fake_stripe)) == sent
        assert CardHold.objects.get().stripe_payment_intent_id == payment_intent_id
        assert fake_stripe.live_authorizations() == [payment_intent_id]

    def test_a_duplicate_event_changes_nothing(
        self, holder, fake_stripe, deferral, client, django_capture_on_commit_callbacks
    ) -> None:
        hold, payment_intent_id = lost_placement(holder, fake_stripe)
        deliver(
            client, fake_stripe, AUTHORIZED, payment_intent_id, django_capture_on_commit_callbacks
        )
        before = reload(hold)

        deliver(
            client, fake_stripe, AUTHORIZED, payment_intent_id, django_capture_on_commit_callbacks
        )

        after = reload(hold)
        assert after.status == CardHold.Status.AUTHORIZED
        assert after.modified == before.modified
        assert after.stray_payment_intent_ids == []
        assert fake_stripe.calls_to("PaymentIntent.cancel") == []

    def test_events_out_of_order_settle_on_the_live_state(
        self, holder, order, fake_stripe, client, django_capture_on_commit_callbacks
    ) -> None:
        """A stale ``amount_capturable_updated`` after the cancel confirms the release
        (the PaymentIntent is read live), and a ``canceled`` arriving first does too."""
        payment_intent = fake_stripe.PaymentIntent.create(
            amount=11_000,
            currency="usd",
            customer=STRIPE_CUSTOMER_ID,
            payment_method="pm_visa",
            capture_method="manual",
        )
        hold = CardHoldFactory(
            target=order,
            stripe_payment_intent_id=payment_intent.id,
            status=CardHold.Status.RELEASED,
            release_reason=CardHold.ReleaseReason.CANCELLED,
        )
        fake_stripe.intents[payment_intent.id]["metadata"]["card_hold_id"] = str(hold.pk)
        stale = fake_stripe.event(AUTHORIZED, payment_intent.id)
        fake_stripe.set_status(payment_intent.id, "canceled")

        with django_capture_on_commit_callbacks(execute=True):
            assert deliver_event(client, stale).status_code == 200

        assert reload(hold).release_confirmed_at is not None
        deliver(
            client, fake_stripe, CANCELED, payment_intent.id, django_capture_on_commit_callbacks
        )
        assert reload(hold).release_confirmed_at is not None
        assert fake_stripe.calls_to("PaymentIntent.cancel") == []


class TestStrays:
    def stray(self, fake_stripe, hold, amount: int = 11_000) -> str:
        """An authorization naming ``hold`` that it doesn't carry (an old key's orphan)."""
        payment_intent = fake_stripe.PaymentIntent.create(
            amount=amount,
            currency="usd",
            customer=STRIPE_CUSTOMER_ID,
            payment_method="pm_visa",
            capture_method="manual",
            metadata={"card_hold_id": str(hold.pk)},
        )
        return payment_intent.id

    def test_a_stray_authorization_is_cancelled(
        self, holder, order, fake_stripe, client, django_capture_on_commit_callbacks
    ) -> None:
        hold = CardHoldFactory(target=order)
        stray = self.stray(fake_stripe, hold)

        deliver(client, fake_stripe, AUTHORIZED, stray, django_capture_on_commit_callbacks)

        assert fake_stripe.status_of(stray) == "canceled"
        hold = reload(hold)
        assert hold.status == CardHold.Status.AUTHORIZED  # its own hold is untouched
        assert hold.stray_payment_intent_ids == []

    def test_a_lost_cancel_is_re_driven_by_the_sweep_until_confirmed(
        self, holder, order, fake_stripe, client, django_capture_on_commit_callbacks
    ) -> None:
        hold = CardHoldFactory(target=order)
        stray = self.stray(fake_stripe, hold)
        with patch.object(holds, "release_on_commit"):  # the broker lost the task
            deliver(client, fake_stripe, AUTHORIZED, stray, django_capture_on_commit_callbacks)
        assert reload(hold).stray_payment_intent_ids == [stray]
        assert fake_stripe.status_of(stray) == "requires_capture"
        # A repeat of the event doesn't queue it twice: the sweep owns it now.
        with patch.object(holds, "release_on_commit") as queued:
            deliver(client, fake_stripe, AUTHORIZED, stray, django_capture_on_commit_callbacks)
        queued.assert_not_called()

        sweep_card_holds()  # within the grace: its own task may still be queued
        assert fake_stripe.status_of(stray) == "requires_capture"
        CardHold.objects.filter(pk=hold.pk).update(
            modified=timezone.now() - datetime.timedelta(hours=1)
        )
        fake_stripe.fail_next("PaymentIntent.cancel", stripe.InvalidRequestError("no", None))
        sweep_card_holds()  # refused: still tracked
        assert reload(hold).stray_payment_intent_ids == [stray]
        CardHold.objects.filter(pk=hold.pk).update(
            modified=timezone.now() - datetime.timedelta(hours=1)
        )

        sweep_card_holds()

        assert fake_stripe.status_of(stray) == "canceled"
        assert reload(hold).stray_payment_intent_ids == []

    def test_a_canceled_event_confirms_a_stray(
        self, holder, order, fake_stripe, client, django_capture_on_commit_callbacks
    ) -> None:
        hold = CardHoldFactory(target=order)
        stray = self.stray(fake_stripe, hold)
        CardHold.objects.filter(pk=hold.pk).update(stray_payment_intent_ids=[stray])
        fake_stripe.set_status(stray, "canceled")

        deliver(client, fake_stripe, CANCELED, stray, django_capture_on_commit_callbacks)

        assert reload(hold).stray_payment_intent_ids == []

    def test_an_authorization_of_another_amount_isnt_the_placements(
        self, holder, fake_stripe, deferral, django_capture_on_commit_callbacks
    ) -> None:
        hold = due(holder, placement_key="k-out", placement_amount_cents=11_000)
        stray = self.stray(fake_stripe, hold, amount=5_000)

        with django_capture_on_commit_callbacks(execute=True):
            assert reconcile_payment_intent(hold.pk, stray) == "stray"

        hold = reload(hold)
        assert hold.status == CardHold.Status.SCHEDULED and hold.placement_key == "k-out"
        assert fake_stripe.status_of(stray) == "canceled"

    def test_a_captured_stray_is_logged_and_dropped(
        self, holder, order, fake_stripe, caplog
    ) -> None:
        hold = CardHoldFactory(target=order)
        stray = self.stray(fake_stripe, hold)
        CardHold.objects.filter(pk=hold.pk).update(stray_payment_intent_ids=[stray])
        fake_stripe.set_status(stray, "succeeded")

        assert holds.release(hold.pk, claimed=True, payment_intent_id=stray) is False
        assert reconcile_payment_intent(hold.pk, stray) == "ignored"

        assert reload(hold).stray_payment_intent_ids == []
        assert "was captured" in caplog.text

    def test_an_unknown_captured_payment_intent_is_logged(
        self, holder, order, fake_stripe, caplog
    ) -> None:
        hold = CardHoldFactory(target=order)
        stray = self.stray(fake_stripe, hold)
        fake_stripe.set_status(stray, "succeeded")

        assert reconcile_payment_intent(hold.pk, stray) == "ignored"
        assert "was captured; check Stripe" in caplog.text


class TestOtherEvents:
    def test_a_capture_is_recorded(
        self, holder, order, fake_stripe, client, django_capture_on_commit_callbacks
    ) -> None:
        payment_intent = fake_stripe.PaymentIntent.create(
            amount=11_000, currency="usd", customer=STRIPE_CUSTOMER_ID, payment_method="pm_visa"
        )
        hold = CardHoldFactory(target=order, stripe_payment_intent_id=payment_intent.id)
        fake_stripe.intents[payment_intent.id]["metadata"]["card_hold_id"] = str(hold.pk)
        fake_stripe.PaymentIntent.capture(payment_intent.id, amount_to_capture=9_000)

        deliver(
            client, fake_stripe, SUCCEEDED, payment_intent.id, django_capture_on_commit_callbacks
        )

        hold = reload(hold)
        assert hold.status == CardHold.Status.CAPTURED
        assert hold.captured_amount_cents == 9_000

    def test_a_decline_of_the_outstanding_placement_fails_the_hold(
        self, holder, fake_stripe, deferral, client, django_capture_on_commit_callbacks
    ) -> None:
        hold = due(holder)
        fake_stripe.next_outcome = ["requires_payment_method"]
        fake_stripe.fail_behind_next()
        place_scheduled(hold.pk)
        (payment_intent_id,) = fake_stripe.intents
        fake_stripe.intents[payment_intent_id]["last_payment_error"] = {
            "code": "card_declined",
            "decline_code": "insufficient_funds",
        }

        deliver(client, fake_stripe, FAILED, payment_intent_id, django_capture_on_commit_callbacks)

        hold = reload(hold)
        assert hold.status == CardHold.Status.FAILED
        assert hold.failure_code == "insufficient_funds"
        assert hold.stripe_payment_intent_id == payment_intent_id

    def test_a_decline_that_isnt_the_outstanding_placement_is_ignored(
        self, holder, order, fake_stripe
    ) -> None:
        hold = CardHoldFactory(target=order)
        payment_intent = fake_stripe.PaymentIntent.create(
            amount=11_000,
            currency="usd",
            customer=STRIPE_CUSTOMER_ID,
            payment_method="pm_visa",
            metadata={"card_hold_id": str(hold.pk)},
        )
        fake_stripe.set_status(payment_intent.id, "requires_payment_method")

        assert reconcile_payment_intent(hold.pk, payment_intent.id) == "ignored"
        assert reload(hold).status == CardHold.Status.AUTHORIZED

    def test_an_on_session_decline_behind_a_5xx_closes_the_attempt(
        self, holder, fake_stripe, django_capture_on_commit_callbacks
    ) -> None:
        attempt_id = uuid.uuid4()
        fake_stripe.next_outcome = ["requires_payment_method"]
        fake_stripe.fail_behind_next()
        first_pass(holder, new_order(holder), attempt_id)
        (payment_intent_id,) = fake_stripe.intents
        hold = CardHold.objects.get()

        with django_capture_on_commit_callbacks(execute=True):
            assert reconcile_payment_intent(hold.pk, payment_intent_id) == "declined"

        hold = reload(hold)
        assert hold.status == CardHold.Status.RELEASED
        assert hold.stripe_payment_intent_id == payment_intent_id
        assert first_pass(holder, new_order(holder), attempt_id).status == (
            PlacementStatus.DECLINED
        )

    def test_a_payment_intent_that_names_another_hold_or_customer_is_ignored(
        self, holder, order, fake_stripe
    ) -> None:
        hold = CardHoldFactory(target=order)
        other = fake_stripe.PaymentIntent.create(
            amount=11_000,
            currency="usd",
            customer="cus_someone_else",
            payment_method="pm_visa",
            metadata={"card_hold_id": str(hold.pk)},
        )

        assert reconcile_payment_intent(hold.pk + 1, other.id) == "ignored"
        assert reconcile_payment_intent(hold.pk, other.id) == "ignored"
        assert reconcile_payment_intent(hold.pk, "pi_missing") == "ignored"
        CardHold.objects.filter(pk=hold.pk).delete()
        assert reconcile_payment_intent(hold.pk, other.id) == "ignored"
        assert fake_stripe.calls_to("PaymentIntent.cancel") == []

    def test_a_hold_of_an_unregistered_target_is_left_alone(
        self, holder, order, fake_stripe
    ) -> None:
        hold = CardHoldFactory(target=order)
        stray = TestStrays().stray(fake_stripe, hold)

        with patch.object(holds, "target_for_content_type_id", return_value=None):
            assert reconcile_payment_intent(hold.pk, stray) == "ignored"

    def test_a_row_that_moves_under_the_lock_is_looked_up_again(
        self, holder, order, fake_stripe
    ) -> None:
        hold = CardHoldFactory(target=order)
        stray = TestStrays().stray(fake_stripe, hold)

        with patch.object(holds, "_lock_target_and_hold", return_value=(order, None)):
            assert reconcile_payment_intent(hold.pk, stray) == "ignored"


class TestTheWebhook:
    def test_without_card_holds_the_events_cost_nothing(
        self, holder, order, fake_stripe, django_assert_num_queries
    ) -> None:
        hold = CardHoldFactory(target=order)
        event = {
            "type": AUTHORIZED,
            "data": {"object": {"id": "pi_x", "metadata": {"card_hold_id": str(hold.pk)}}},
        }
        with (
            patch("baseapp_payments.models.card_holds_enabled", return_value=False),
            patch.object(reconcile_card_hold, "delay") as queued,
            django_assert_num_queries(0),
        ):
            response = StripeWebhookHandler().card_hold_payment_intent(event)

        assert response.status_code == 200
        queued.assert_not_called()

    def test_an_event_without_card_hold_id_is_ignored(
        self, fake_stripe, client, django_assert_num_queries
    ) -> None:
        payment_intent = fake_stripe.PaymentIntent.create(
            amount=500, currency="usd", customer=STRIPE_CUSTOMER_ID, payment_method="pm_visa"
        )
        with patch.object(reconcile_card_hold, "delay") as queued:
            response = deliver_event(client, fake_stripe.event(SUCCEEDED, payment_intent.id))

        assert response.status_code == 200
        queued.assert_not_called()

    def test_a_broker_error_answers_500_so_stripe_redelivers(self, fake_stripe, client) -> None:
        event = {
            "type": CANCELED,
            "data": {"object": {"id": "pi_x", "metadata": {"card_hold_id": "7"}}},
        }
        with patch.object(reconcile_card_hold, "delay", side_effect=OSError("broker down")):
            response = StripeWebhookHandler().card_hold_payment_intent(event)

        assert response.status_code == 500

    def test_a_bad_signature_is_refused(self, fake_stripe, client) -> None:
        payment_intent = fake_stripe.PaymentIntent.create(
            amount=500, currency="usd", customer=STRIPE_CUSTOMER_ID, payment_method="pm_visa"
        )
        response = deliver_event(
            client, fake_stripe.event(AUTHORIZED, payment_intent.id), secret="whsec_wrong"
        )
        assert response.status_code == 400

    def test_customer_events_still_reach_their_handlers(self, holder, client) -> None:
        Customer = swapper.load_model("baseapp_payments", "Customer")
        event = {
            "id": "evt_1",
            "object": "event",
            "type": "customer.created",
            "data": {
                "object": {"id": "cus_signed", "metadata": {"entity_id": str(holder.profile.id)}}
            },
        }

        assert deliver_event(client, event).status_code == 200
        assert Customer.objects.get(remote_customer_id="cus_signed").entity == holder.profile

    def test_the_task_retries_stripes_transient_errors_then_gives_up(
        self, fake_stripe, eager_retries, caplog
    ) -> None:
        with patch.object(holds, "retrieve_payment_intent", side_effect=connection_error()):
            reconcile_card_hold.delay(1, payment_intent_id="pi_x")

        assert "Gave up reconciling card hold 1" in caplog.text

    def test_the_task_is_a_no_op_without_stripe(self, no_stripe_key) -> None:
        with patch.object(holds, "reconcile_payment_intent") as reconcile:
            reconcile_card_hold.delay(1, payment_intent_id="pi_x")
        reconcile.assert_not_called()


class TestLookup:
    def test_nothing_found_rotates_the_key_and_the_hold_places_once(
        self, holder, fake_stripe, deferral
    ) -> None:
        hold = due(holder)
        fake_stripe.fail_next("PaymentIntent.create", api_error())  # nothing behind it
        place_scheduled(hold.pk)
        old_key = reload(hold).placement_key
        age(hold)

        assert place_scheduled(hold.pk).status == PlacementStatus.IN_PROGRESS

        hold = reload(hold)
        assert hold.status == CardHold.Status.SCHEDULED
        assert hold.placement_key == "" and hold.placement_sent_at is None
        assert hold.placement_generation == 1
        assert fake_stripe.intents == {}

        sweep_card_holds()
        sweep_card_holds()

        hold = reload(hold)
        assert hold.status == CardHold.Status.AUTHORIZED
        assert [params["idempotency_key"] for params in creates(fake_stripe)] == [
            old_key,
            f"{old_key}-1",
        ]
        assert len(fake_stripe.live_authorizations()) == 1

    def test_search_unavailable_falls_back_to_listing(self, holder, fake_stripe, deferral) -> None:
        hold, payment_intent_id = lost_placement(holder, fake_stripe)
        age(hold)
        fake_stripe.fail_next(
            "PaymentIntent.search",
            stripe.InvalidRequestError("Search is not available in your region.", None),
        )

        place_scheduled(hold.pk)

        ((_args, listed),) = fake_stripe.calls_to("PaymentIntent.list")
        assert listed["customer"] == STRIPE_CUSTOMER_ID
        assert reload(hold).stripe_payment_intent_id == payment_intent_id

    def test_listing_needs_a_customer(self, holder) -> None:
        hold = CardHoldFactory(stripe_customer_id="")
        with patch.object(holds.utils, "get_stripe") as get_stripe:
            get_stripe.return_value.PaymentIntent.search.side_effect = stripe.PermissionError("no")
            assert find_hold_payment_intents(hold) == []
            get_stripe.return_value.PaymentIntent.list.assert_not_called()

    def test_a_lookup_error_leaves_the_claim_for_the_next_sweep(
        self, holder, fake_stripe, deferral
    ) -> None:
        hold, _payment_intent_id = lost_placement(holder, fake_stripe)
        age(hold)
        fake_stripe.fail_next("PaymentIntent.search", connection_error())

        assert place_scheduled(hold.pk).status == PlacementStatus.IN_PROGRESS

        hold = reload(hold)
        assert hold.placement_key and hold.placement_claimed_at is None

    def test_the_project_can_swap_the_lookup(self, holder, fake_stripe, deferral) -> None:
        hold, payment_intent_id = lost_placement(holder, fake_stripe)
        age(hold)
        found = [fake_stripe.PaymentIntent.retrieve(payment_intent_id)]

        with (
            override_settings(BASEAPP_PAYMENTS_CARD_HOLD_LOOKUP=f"{__name__}._found"),
            patch(f"{__name__}._found", return_value=found, create=True),
        ):
            assert place_scheduled(hold.pk).status == PlacementStatus.PLACED

        assert fake_stripe.calls_to("PaymentIntent.search") == []

    def test_a_found_authorization_for_a_target_not_holdable_is_released(
        self, holder, fake_stripe, deferral, django_capture_on_commit_callbacks
    ) -> None:
        hold, payment_intent_id = lost_placement(holder, fake_stripe)
        age(hold)
        HoldableOrder.objects.filter(pk=hold.target.pk).update(status="cancelled")

        with django_capture_on_commit_callbacks(execute=True):
            assert place_scheduled(hold.pk).status == PlacementStatus.REFUSED

        assert fake_stripe.status_of(payment_intent_id) == "canceled"

    def test_a_found_decline_fails_the_hold(self, holder, fake_stripe, deferral) -> None:
        hold = due(holder)
        fake_stripe.next_outcome = ["requires_payment_method"]
        fake_stripe.fail_behind_next()
        place_scheduled(hold.pk)
        age(hold)

        assert place_scheduled(hold.pk).status == PlacementStatus.DECLINED
        assert reload(hold).status == CardHold.Status.FAILED

    def test_a_reconcile_whose_hold_moved_meanwhile_does_nothing(
        self, holder, fake_stripe, deferral
    ) -> None:
        hold, _payment_intent_id = lost_placement(holder, fake_stripe)
        age(hold)

        real = holds._lock_target_and_hold
        calls = []

        def moved_on_reconcile(*args, **kwargs) -> tuple:
            calls.append(args)
            return real(*args, **kwargs) if len(calls) == 1 else (None, None)

        with patch.object(holds, "_lock_target_and_hold", side_effect=moved_on_reconcile):
            assert place_scheduled(hold.pk).status == PlacementStatus.IN_PROGRESS

    def test_a_key_with_no_recorded_first_send_is_counted_from_its_next_claim(
        self, holder, fake_stripe, deferral
    ) -> None:
        hold = due(holder, placement_key="k-legacy", placement_amount_cents=11_000)

        place_scheduled(hold.pk)

        assert reload(hold).status == CardHold.Status.AUTHORIZED
        assert creates(fake_stripe)[0]["idempotency_key"] == "k-legacy"


class TestOnSessionStaleRow:
    def test_a_stale_row_answers_in_progress_then_the_client_starts_again(
        self, holder, fake_stripe, django_capture_on_commit_callbacks
    ) -> None:
        attempt_id = uuid.uuid4()
        fake_stripe.fail_behind_next()
        assert first_pass(holder, new_order(holder), attempt_id).status == (
            PlacementStatus.IN_PROGRESS
        )
        (behind,) = fake_stripe.intents
        hold = CardHold.objects.get()
        assert fake_stripe.intents[behind]["metadata"]["card_hold_id"] == str(hold.pk)
        sweep_card_holds()  # not an orphan, and not stale yet: left alone
        assert reload(hold).status == CardHold.Status.PENDING
        age(hold)
        fake_stripe.prune_keys()
        sent = len(creates(fake_stripe))

        # Never replayed blind: the retry waits for reconciliation.
        assert first_pass(holder, new_order(holder), attempt_id).status == (
            PlacementStatus.IN_PROGRESS
        )
        assert len(creates(fake_stripe)) == sent

        with django_capture_on_commit_callbacks(execute=True):
            sweep_card_holds()

        hold = reload(hold)
        assert hold.status == CardHold.Status.RELEASED and hold.placement_key == ""
        assert fake_stripe.status_of(behind) == "canceled"
        assert hold.stray_payment_intent_ids == []
        assert first_pass(holder, new_order(holder), attempt_id).status == (
            PlacementStatus.DECLINED
        )
        assert first_pass(holder, new_order(holder), uuid.uuid4()).status == (
            PlacementStatus.PLACED
        )
        assert len(fake_stripe.live_authorizations()) == 1

    def test_a_stale_row_with_nothing_in_stripe_is_just_closed(self, holder, fake_stripe) -> None:
        attempt_id = uuid.uuid4()
        fake_stripe.fail_next("PaymentIntent.create", connection_error())
        fake_stripe.fail_next("PaymentIntent.create", connection_error())
        first_pass(holder, new_order(holder), attempt_id)
        hold = CardHold.objects.get()
        age(hold)

        assert reconcile_stale_send(hold.pk) is True

        hold = reload(hold)
        assert hold.status == CardHold.Status.RELEASED
        assert hold.release_confirmed_at is not None
        assert reconcile_stale_send(hold.pk) is False  # closed: nothing left to claim

    def test_a_lookup_error_leaves_the_row_for_the_next_sweep(self, holder, fake_stripe) -> None:
        fake_stripe.fail_next("PaymentIntent.create", connection_error())
        fake_stripe.fail_next("PaymentIntent.create", connection_error())
        first_pass(holder, new_order(holder), uuid.uuid4())
        hold = CardHold.objects.get()
        age(hold)
        fake_stripe.fail_next("PaymentIntent.search", connection_error())

        assert reconcile_stale_send(hold.pk) is False

        hold = reload(hold)
        assert hold.status == CardHold.Status.PENDING and hold.placement_claimed_at is None

    def test_a_row_closed_between_lookup_and_lock_is_left(self, holder, fake_stripe) -> None:
        fake_stripe.fail_next("PaymentIntent.create", connection_error())
        fake_stripe.fail_next("PaymentIntent.create", connection_error())
        first_pass(holder, new_order(holder), uuid.uuid4())
        hold = CardHold.objects.get()
        age(hold)

        def close_meanwhile(found_for) -> list:
            holds._close_send(found_for.pk)
            return []

        with patch.object(holds, "_lookup", side_effect=close_meanwhile):
            assert reconcile_stale_send(hold.pk) is False

    def test_the_sweep_queues_it_once_its_key_is_stale(self, holder, fake_stripe) -> None:
        fake_stripe.fail_next("PaymentIntent.create", connection_error())
        fake_stripe.fail_next("PaymentIntent.create", connection_error())
        first_pass(holder, new_order(holder), uuid.uuid4())
        hold = CardHold.objects.get()
        CardHold.objects.filter(pk=hold.pk).update(
            created=timezone.now() - datetime.timedelta(hours=1)
        )

        with patch.object(tasks.reconcile_card_hold, "delay") as queued:
            sweep_card_holds()
        queued.assert_not_called()
        age(hold)
        with patch.object(tasks.reconcile_card_hold, "delay") as queued:
            sweep_card_holds()
        queued.assert_called_once_with(hold.pk)


def test_a_found_authorization_another_row_carries_is_left_to_that_row(
    holder, order, fake_stripe, deferral
) -> None:
    hold, payment_intent_id = lost_placement(holder, fake_stripe)
    CardHoldFactory(stripe_payment_intent_id=payment_intent_id, status=CardHold.Status.RELEASED)
    age(hold)

    place_scheduled(hold.pk)

    hold = reload(hold)
    assert hold.status == CardHold.Status.SCHEDULED and hold.placement_generation == 1
    assert hold.stray_payment_intent_ids == []


def test_a_target_not_holdable_at_adoption_goes_back_to_scheduled_later(
    holder, fake_stripe, deferral, client, django_capture_on_commit_callbacks
) -> None:
    hold, payment_intent_id = lost_placement(holder, fake_stripe)

    with patch.object(
        HoldableOrderHoldTarget, "filter_holdable", lambda self, queryset: queryset.none()
    ):
        deliver(
            client, fake_stripe, AUTHORIZED, payment_intent_id, django_capture_on_commit_callbacks
        )

    hold = reload(hold)
    assert hold.status == CardHold.Status.RELEASED
    assert hold.release_reason == CardHold.ReleaseReason.NOT_HOLDABLE
    assert fake_stripe.status_of(payment_intent_id) == "canceled"
    assert hold.release_confirmed_at is not None

    # Holdable again, its date moved out: the sweep puts the same row back to scheduled.
    later = timezone.localdate() + datetime.timedelta(days=10)
    HoldableOrder.objects.filter(pk=hold.target.pk).update(target_date=later)
    with django_capture_on_commit_callbacks(execute=True):
        sweep_card_holds()

    hold = reload(hold)
    assert hold.status == CardHold.Status.SCHEDULED
    assert hold.release_reason == "" and hold.stripe_payment_intent_id is None
    assert hold.previous_payment_intent_ids == [payment_intent_id]
    assert hold.hold_on == later - datetime.timedelta(days=4)


class TestTheAttemptsRow:
    def test_a_concurrent_pass_that_wrote_the_row_first_is_in_progress(
        self, holder, fake_stripe
    ) -> None:
        attempt_id = uuid.uuid4()
        # Another pass holds the key's row (its unique constraint), not visible as ours.
        CardHoldFactory(
            customer=holder,
            status=CardHold.Status.RELEASED,
            stripe_payment_intent_id=None,
            placement_key=holds.idempotency_key(holder, attempt_id),
        )

        assert first_pass(holder, new_order(holder), attempt_id).status == (
            PlacementStatus.IN_PROGRESS
        )
        assert creates(fake_stripe) == []

    def test_a_replayed_create_is_re_read(self, holder, fake_stripe) -> None:
        with patch.object(holds, "is_idempotent_replay", return_value=True):
            result = first_pass(holder, new_order(holder), uuid.uuid4())

        assert result.status == PlacementStatus.PLACED
        assert fake_stripe.calls_to("PaymentIntent.retrieve")

    def test_a_decline_without_a_payment_intent_closes_the_row(self, holder, fake_stripe) -> None:
        from ..fakes import card_declined

        attempt_id = uuid.uuid4()
        fake_stripe.fail_next("PaymentIntent.create", card_declined())

        assert first_pass(holder, new_order(holder), attempt_id).status == (
            PlacementStatus.DECLINED
        )

        hold = CardHold.objects.get()
        assert hold.status == CardHold.Status.RELEASED and hold.placement_key == ""
        assert hold.release_confirmed_at is not None

    def test_a_decline_lands_on_the_attempts_row(
        self, holder, fake_stripe, django_capture_on_commit_callbacks
    ) -> None:
        fake_stripe.next_outcome = ["card_declined"]

        with django_capture_on_commit_callbacks(execute=True):
            first_pass(holder, new_order(holder), uuid.uuid4())

        hold = CardHold.objects.get()
        assert hold.status == CardHold.Status.RELEASED
        assert fake_stripe.status_of(hold.stripe_payment_intent_id) == "canceled"

    def test_forgetting_what_isnt_a_stray_changes_nothing(self, holder, order) -> None:
        hold = CardHoldFactory(target=order, stray_payment_intent_ids=["pi_a"])

        holds._forget_stray(hold.pk, "pi_b")

        assert reload(hold).stray_payment_intent_ids == ["pi_a"]


class TestAnOvertakenPlacementsOwnPaymentIntent:
    """The placement's create answered after a webhook or lookup had already settled the
    hold with another PaymentIntent: what this create made is cancelled as a stray,
    never dropped."""

    def overtake(self, fake_stripe, settle_with: str | None = None) -> Any:
        """Patch the create so that, once Stripe answers, the hold is found settled with
        ``settle_with`` (the create's own PaymentIntent when ``None``)."""
        real = holds._create_off_session

        def create_then_overtaken(hold) -> tuple[Any, Exception | None]:
            payment_intent, error = real(hold)
            CardHold.objects.filter(pk=hold.pk).update(
                status=CardHold.Status.AUTHORIZED,
                stripe_payment_intent_id=settle_with or payment_intent["id"],
                placement_key="",
                placement_amount_cents=None,
                placement_sent_at=None,
                placement_claimed_at=None,
            )
            return payment_intent, error

        return patch.object(holds, "_create_off_session", side_effect=create_then_overtaken)

    def test_it_is_tracked_and_cancelled_after_the_commit(
        self, holder, fake_stripe, deferral, django_capture_on_commit_callbacks
    ) -> None:
        hold = due(holder)

        with (
            self.overtake(fake_stripe, "pi_from_the_webhook"),
            django_capture_on_commit_callbacks(execute=True),
        ):
            assert place_scheduled(hold.pk).status == PlacementStatus.IN_PROGRESS

        (own,) = fake_stripe.intents
        assert fake_stripe.status_of(own) == "canceled"
        hold = reload(hold)
        assert hold.status == CardHold.Status.AUTHORIZED
        assert hold.stripe_payment_intent_id == "pi_from_the_webhook"
        assert hold.stray_payment_intent_ids == []  # Stripe confirmed the cancel

    def test_the_sweep_re_drives_a_cancel_that_didnt_run(
        self, holder, fake_stripe, deferral
    ) -> None:
        hold = due(holder)

        with (
            self.overtake(fake_stripe, "pi_from_the_webhook"),
            patch.object(holds, "release_on_commit"),
        ):
            place_scheduled(hold.pk)

        (own,) = fake_stripe.intents
        hold = reload(hold)
        assert hold.stray_payment_intent_ids == [own]
        CardHold.objects.filter(pk=hold.pk).update(
            modified=timezone.now() - datetime.timedelta(hours=1)
        )
        with patch.object(tasks.release_card_hold, "delay") as queued:
            sweep_card_holds()
        queued.assert_any_call(hold.pk, claimed=True, payment_intent_id=own)

    def test_one_the_hold_now_carries_is_left_alone(
        self, holder, fake_stripe, deferral, django_capture_on_commit_callbacks
    ) -> None:
        hold = due(holder)

        with self.overtake(fake_stripe), django_capture_on_commit_callbacks(execute=True):
            place_scheduled(hold.pk)

        (own,) = fake_stripe.intents
        assert fake_stripe.status_of(own) == "requires_capture"
        hold = reload(hold)
        assert hold.stripe_payment_intent_id == own and hold.stray_payment_intent_ids == []

    def test_no_payment_intent_leaves_nothing_to_track(self, holder, fake_stripe, deferral) -> None:
        hold = due(holder)
        fake_stripe.fail_next("PaymentIntent.create", connection_error())

        with self.overtake(fake_stripe, "pi_from_the_webhook"):
            assert place_scheduled(hold.pk).status == PlacementStatus.IN_PROGRESS

        assert reload(hold).stray_payment_intent_ids == []
