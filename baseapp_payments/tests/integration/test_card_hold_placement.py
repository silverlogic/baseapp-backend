"""Placing a card hold while the customer is present (authorize_on_session /
complete_on_session). Stripe is the in-memory ``FakeStripe``."""

import datetime
import uuid
from collections.abc import Callable
from decimal import Decimal
from typing import Any
from unittest.mock import patch

import pytest
import stripe
import swapper
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from baseapp_core.models import DocumentId
from baseapp_payments import holds
from baseapp_payments.holds import (
    HoldRefused,
    PlacementResult,
    PlacementStatus,
    abandon_hold,
    authorize_on_session,
    complete_on_session,
    find_placed,
)
from baseapp_payments.signals import card_hold_authorized, card_hold_released
from testproject.testapp.card_holds import HoldableOrderHoldTarget
from testproject.testapp.models import HoldableOrder

from ..factories import CardHoldFactory, HoldableOrderFactory, UserFactory
from ..fakes import (
    CAPTURE_BEFORE,
    STRIPE_CUSTOMER_ID,
    api_error,
    concurrent_request,
    connection_error,
    rate_limited,
)

CardHold = swapper.load_model("baseapp_payments", "CardHold")

pytestmark = pytest.mark.django_db


def new_order(holder, amount_cents: int = 10_000, **fields) -> HoldableOrder:
    """An unsaved order, charged in two days: what a project validates its input into."""
    fields.setdefault("target_date", timezone.localdate() + datetime.timedelta(days=2))
    return HoldableOrder(user=holder, amount_cents=amount_cents, **fields)


def saving(order: HoldableOrder) -> Callable[[Any], HoldableOrder]:
    def link(hold) -> HoldableOrder:
        order.save()
        return order

    return link


def place(holder, order, attempt_id, *, link=None, **kwargs) -> PlacementResult:
    kwargs.setdefault("payment_method_id", "pm_visa")
    kwargs.setdefault("stripe_customer_id", STRIPE_CUSTOMER_ID)
    kwargs.setdefault("expected_amount_cents", order.amount_cents)
    if link is None and order.pk is None:
        link = saving(order)
    return authorize_on_session(
        user=holder, attempt_id=attempt_id, target=order, link=link, **kwargs
    )


@pytest.fixture
def attempt_id() -> uuid.UUID:
    return uuid.uuid4()


class TestFirstPass:
    def test_a_saved_card_authorizes_and_places(
        self, holder, attempt_id, fake_stripe, django_capture_on_commit_callbacks
    ) -> None:
        order = new_order(holder)
        authorized = []
        card_hold_authorized.connect(
            lambda **kwargs: authorized.append(kwargs), weak=False, dispatch_uid="t-auth"
        )
        try:
            with django_capture_on_commit_callbacks(execute=True):
                result = place(holder, order, attempt_id)
        finally:
            card_hold_authorized.disconnect(dispatch_uid="t-auth")

        assert result.status == PlacementStatus.PLACED
        assert result.target == order and order.pk is not None
        hold = CardHold.objects.get()
        assert hold.target == order
        assert hold.status == CardHold.Status.AUTHORIZED
        assert hold.customer == holder
        assert hold.stripe_customer_id == STRIPE_CUSTOMER_ID
        assert (hold.estimated_amount_cents, hold.buffer_percent, hold.amount_cents) == (
            10_000,
            Decimal("10.00"),
            11_000,
        )
        assert hold.expires_at == datetime.datetime.fromtimestamp(
            CAPTURE_BEFORE, tz=datetime.timezone.utc
        )
        assert (hold.card_brand, hold.card_last4, hold.card_funding, hold.card_fingerprint) == (
            "visa",
            "4242",
            "credit",
            "fp_visa",
        )
        ((_args, params),) = fake_stripe.calls_to("PaymentIntent.create")
        assert params["amount"] == 11_000
        assert params["payment_method_types"] == ["card"]
        assert params["capture_method"] == "manual"
        assert params["confirm"] is True
        assert params["idempotency_key"] == f"testproject-hold-{holder.pk}-{attempt_id}"
        assert params["metadata"] == {
            "user_id": str(holder.pk),
            "attempt_id": str(attempt_id),
            "card_hold_id": str(hold.pk),
        }
        assert "setup_future_usage" not in params
        assert authorized[0]["hold"] == hold and authorized[0]["target"] == order

    def test_the_target_buffer_overrides_the_default(self, holder, attempt_id, fake_stripe) -> None:
        order = new_order(holder, buffer_percent=Decimal("25"))

        place(holder, order, attempt_id)

        assert CardHold.objects.get().amount_cents == 12_500

    def test_a_new_card_is_saved_for_off_session_use(self, holder, attempt_id, fake_stripe) -> None:
        fake_stripe.add_card("pm_new", customer=None)

        place(holder, new_order(holder), attempt_id, payment_method_id="pm_new")

        ((_args, params),) = fake_stripe.calls_to("PaymentIntent.create")
        assert params["setup_future_usage"] == "off_session"

    def test_a_missing_capture_before_falls_back_to_seven_days(
        self, holder, attempt_id, fake_stripe, caplog
    ) -> None:
        fake_stripe.capture_before = None

        place(holder, new_order(holder), attempt_id)

        hold = CardHold.objects.get()
        assert (
            datetime.timedelta(days=6, hours=23)
            < hold.expires_at - hold.created
            < datetime.timedelta(days=7, minutes=1)
        )
        assert "assuming a hold of 7 days" in caplog.text

    def test_a_placed_attempt_returns_its_target_before_any_check(
        self, holder, attempt_id, fake_stripe, no_stripe_key
    ) -> None:
        order = HoldableOrderFactory(user=holder)
        CardHoldFactory(target=order, attempt_id=attempt_id)

        result = place(holder, new_order(holder, amount_cents=1), attempt_id)

        assert result.status == PlacementStatus.PLACED
        assert result.target == order
        assert fake_stripe.calls == []
        assert find_placed(holder, attempt_id) == order
        assert find_placed(UserFactory(), attempt_id) is None
        assert find_placed(holder, None) is None

    def test_a_price_mismatch_creates_no_payment_intent(
        self, holder, attempt_id, fake_stripe
    ) -> None:
        result = place(holder, new_order(holder), attempt_id, expected_amount_cents=9_999)

        assert result.status == PlacementStatus.AMOUNT_CHANGED
        assert fake_stripe.calls_to("PaymentIntent.create") == []
        assert not HoldableOrder.objects.exists()

    def test_nothing_to_hold_declines(self, holder, attempt_id, fake_stripe) -> None:
        result = place(holder, new_order(holder, amount_cents=0), attempt_id)

        assert result.status == PlacementStatus.DECLINED
        assert fake_stripe.calls_to("PaymentIntent.create") == []

    @pytest.mark.parametrize(
        "card",
        [
            {"customer": "cus_someone_else"},
            {"type": "us_bank_account"},
        ],
    )
    def test_a_card_that_isnt_theirs_or_isnt_a_card_is_refused(
        self, holder, attempt_id, fake_stripe, card
    ) -> None:
        fake_stripe.add_card("pm_other", **card)

        result = place(holder, new_order(holder), attempt_id, payment_method_id="pm_other")

        assert result.status == PlacementStatus.DECLINED
        assert fake_stripe.calls_to("PaymentIntent.create") == []

    def test_an_unknown_payment_method_declines(self, holder, attempt_id, fake_stripe) -> None:
        result = place(holder, new_order(holder), attempt_id, payment_method_id="pm_missing")

        assert result.status == PlacementStatus.DECLINED

    def test_without_a_stripe_key_or_customer_declines(
        self, holder, attempt_id, fake_stripe
    ) -> None:
        assert (
            place(holder, new_order(holder), attempt_id, stripe_customer_id="").status
            == PlacementStatus.DECLINED
        )
        with patch("baseapp_payments.utils.stripe_configured", return_value=False):
            assert place(holder, new_order(holder), attempt_id).status == PlacementStatus.DECLINED
        assert fake_stripe.calls == []

    def test_a_declined_card_records_a_released_hold_and_cancels_it(
        self, holder, attempt_id, fake_stripe, django_capture_on_commit_callbacks
    ) -> None:
        fake_stripe.next_outcome = ["card_declined"]

        with django_capture_on_commit_callbacks(execute=True):
            result = place(holder, new_order(holder), attempt_id)

        assert result.status == PlacementStatus.DECLINED
        hold = CardHold.objects.get()
        assert hold.status == CardHold.Status.RELEASED
        assert hold.target_document is None
        assert fake_stripe.status_of(hold.stripe_payment_intent_id) == "canceled"
        assert not HoldableOrder.objects.exists()

    @pytest.mark.parametrize("outcome", ["requires_payment_method", "processing"])
    def test_any_other_status_releases_the_hold(
        self, holder, attempt_id, fake_stripe, django_capture_on_commit_callbacks, outcome
    ) -> None:
        fake_stripe.next_outcome = [outcome]

        with django_capture_on_commit_callbacks(execute=True):
            result = place(holder, new_order(holder), attempt_id)

        assert result.status == PlacementStatus.DECLINED
        hold = CardHold.objects.get()
        assert hold.status == CardHold.Status.RELEASED
        assert fake_stripe.status_of(hold.stripe_payment_intent_id) == "canceled"


def unanswered() -> Any:
    """The attempt's row, written before its create, still waiting for its answer."""
    hold = CardHold.objects.get()
    assert hold.status == CardHold.Status.PENDING and hold.stripe_payment_intent_id is None
    assert hold.placement_key and hold.placement_sent_at is not None
    return hold


class TestIdempotency:
    def test_a_concurrent_request_with_the_same_key_is_in_progress(
        self, holder, attempt_id, fake_stripe
    ) -> None:
        fake_stripe.fail_next("PaymentIntent.create", concurrent_request())

        result = place(holder, new_order(holder), attempt_id)

        assert result.status == PlacementStatus.IN_PROGRESS
        unanswered()

    def test_the_same_key_with_different_parameters_is_changed(
        self, holder, attempt_id, fake_stripe
    ) -> None:
        fake_stripe.next_outcome = ["requires_action"]
        place(holder, new_order(holder), attempt_id)

        result = place(holder, new_order(holder, amount_cents=20_000), attempt_id)

        assert result.status == PlacementStatus.CHANGED

    def test_no_answer_is_retried_once_with_the_same_key(
        self, holder, attempt_id, fake_stripe
    ) -> None:
        fake_stripe.fail_next("PaymentIntent.create", connection_error())

        result = place(holder, new_order(holder), attempt_id)

        assert result.status == PlacementStatus.PLACED
        keys = [
            params["idempotency_key"] for _a, params in fake_stripe.calls_to("PaymentIntent.create")
        ]
        assert len(keys) == 2 and keys[0] == keys[1]

    def test_no_answer_twice_is_in_progress(self, holder, attempt_id, fake_stripe) -> None:
        fake_stripe.fail_next("PaymentIntent.create", connection_error())
        fake_stripe.fail_next("PaymentIntent.create", connection_error())

        result = place(holder, new_order(holder), attempt_id)

        assert result.status == PlacementStatus.IN_PROGRESS

    def test_a_rate_limit_is_retried_once_with_the_same_key(
        self, holder, attempt_id, fake_stripe
    ) -> None:
        """M4: a 429 is not a decline; Stripe ran nothing, so the retry authorizes."""
        fake_stripe.fail_next("PaymentIntent.create", rate_limited())

        result = place(holder, new_order(holder), attempt_id)

        assert result.status == PlacementStatus.PLACED
        keys = [
            params["idempotency_key"] for _a, params in fake_stripe.calls_to("PaymentIntent.create")
        ]
        assert len(keys) == 2 and keys[0] == keys[1]

    def test_a_server_error_is_in_progress_not_declined(
        self, holder, attempt_id, fake_stripe
    ) -> None:
        """M4: a 5xx may hide an authorization. Stripe replays a 500 for its key, so the
        retry gets it again: ``in_progress``, and the attempt (same key) is retried later."""
        fake_stripe.fail_next("PaymentIntent.create", api_error())

        result = place(holder, new_order(holder), attempt_id)

        assert result.status == PlacementStatus.IN_PROGRESS
        assert len(fake_stripe.calls_to("PaymentIntent.create")) == 2
        unanswered()

    @pytest.mark.parametrize("error", [api_error, rate_limited])
    def test_a_server_error_or_rate_limit_twice_is_in_progress(
        self, holder, attempt_id, fake_stripe, error
    ) -> None:
        fake_stripe.fail_next("PaymentIntent.create", error())
        fake_stripe.fail_next("PaymentIntent.create", error())

        result = place(holder, new_order(holder), attempt_id)

        assert result.status == PlacementStatus.IN_PROGRESS
        unanswered()

    def test_an_error_with_a_response_declines_without_a_retry(
        self, holder, attempt_id, fake_stripe, caplog
    ) -> None:
        fake_stripe.fail_next(
            "PaymentIntent.create",
            stripe.InvalidRequestError("No such customer", "customer", http_status=400),
        )

        result = place(holder, new_order(holder), attempt_id)

        assert result.status == PlacementStatus.DECLINED
        assert len(fake_stripe.calls_to("PaymentIntent.create")) == 1
        assert "Stripe refused the card hold" in caplog.text

    @pytest.mark.parametrize(
        "error",
        [
            stripe.AuthenticationError("Invalid API Key", http_status=401),
            stripe.PermissionError("This key can't do that", http_status=403),
        ],
    )
    def test_a_bad_key_is_in_progress_not_declined(
        self, holder, attempt_id, fake_stripe, caplog, error
    ) -> None:
        """M2: a bad or revoked key says nothing about the card. Not retried (it would
        fail the same way), logged as an error, and the attempt works once it's fixed."""
        fake_stripe.fail_next("PaymentIntent.create", error)

        with caplog.at_level("ERROR", logger="baseapp_payments.holds"):
            result = place(holder, new_order(holder), attempt_id)

        assert result.status == PlacementStatus.IN_PROGRESS
        assert len(fake_stripe.calls_to("PaymentIntent.create")) == 1
        assert "Stripe refused the API key" in caplog.text
        unanswered()
        assert place(holder, new_order(holder), attempt_id).status == PlacementStatus.PLACED

    def test_a_bad_key_reading_the_card_is_in_progress(
        self, holder, attempt_id, fake_stripe, caplog
    ) -> None:
        fake_stripe.fail_next(
            "PaymentMethod.retrieve", stripe.AuthenticationError("Invalid API Key", http_status=401)
        )

        result = place(holder, new_order(holder), attempt_id)

        assert result.status == PlacementStatus.IN_PROGRESS
        assert fake_stripe.calls_to("PaymentIntent.create") == []
        assert "No usable answer reading PaymentMethod" in caplog.text

    def test_a_replay_re_reads_the_payment_intent_and_places_a_live_one(
        self, holder, attempt_id, fake_stripe
    ) -> None:
        fake_stripe.next_outcome = ["requires_action"]
        first = place(holder, new_order(holder), attempt_id)
        assert first.status == PlacementStatus.REQUIRES_ACTION
        (payment_intent_id,) = fake_stripe.intents
        fake_stripe.set_status(payment_intent_id, "requires_capture")  # authenticated

        result = place(holder, new_order(holder), attempt_id)

        assert result.status == PlacementStatus.PLACED
        assert fake_stripe.calls_to("PaymentIntent.retrieve")
        assert CardHold.objects.get().status == CardHold.Status.AUTHORIZED

    def test_a_replayed_authorization_of_an_abandoned_attempt_places_nothing(
        self, holder, attempt_id, fake_stripe, django_capture_on_commit_callbacks
    ) -> None:
        fake_stripe.next_outcome = ["requires_action"]
        place(holder, new_order(holder), attempt_id)
        (payment_intent_id,) = fake_stripe.intents
        fake_stripe.set_status(payment_intent_id, "canceled")

        with django_capture_on_commit_callbacks(execute=True):
            result = place(holder, new_order(holder), attempt_id)

        assert result.status == PlacementStatus.DECLINED
        assert CardHold.objects.get().status == CardHold.Status.RELEASED
        assert not HoldableOrder.objects.exists()

    def test_a_replay_that_cant_be_re_read_is_in_progress(
        self, holder, attempt_id, fake_stripe
    ) -> None:
        fake_stripe.next_outcome = ["requires_action"]
        place(holder, new_order(holder), attempt_id)
        fake_stripe.fail_next("PaymentIntent.retrieve", connection_error())

        result = place(holder, new_order(holder), attempt_id)

        assert result.status == PlacementStatus.IN_PROGRESS

    def test_a_failure_recording_the_hold_cancels_the_authorization(
        self, holder, attempt_id, fake_stripe, django_capture_on_commit_callbacks
    ) -> None:
        with (
            patch.object(holds, "record_pending_hold", side_effect=RuntimeError("db down")),
            django_capture_on_commit_callbacks(execute=True),
            pytest.raises(RuntimeError),
        ):
            place(holder, new_order(holder), attempt_id)

        hold = CardHold.objects.get(stripe_payment_intent_id__isnull=False)
        assert hold.status == CardHold.Status.RELEASED
        assert fake_stripe.status_of(hold.stripe_payment_intent_id) == "canceled"


class TestSecondPass:
    def requires_action(self, holder, attempt_id, fake_stripe, order=None) -> str:
        fake_stripe.next_outcome = ["requires_action"]
        result = place(holder, order or new_order(holder), attempt_id)
        assert result.status == PlacementStatus.REQUIRES_ACTION
        assert result.requires_action
        assert result.intent_type == "payment_intent"
        (payment_intent_id,) = fake_stripe.intents
        assert result.client_secret == f"{payment_intent_id}_secret"
        return payment_intent_id

    def complete(
        self, holder, attempt_id, payment_intent_id, order=None, **kwargs
    ) -> PlacementResult:
        order = order or new_order(holder)
        kwargs.setdefault("stripe_customer_id", STRIPE_CUSTOMER_ID)
        kwargs.setdefault("expected_amount_cents", order.amount_cents)
        return complete_on_session(
            payment_intent_id, saving(order), user=holder, attempt_id=attempt_id, **kwargs
        )

    def test_requires_action_then_the_second_pass_places(
        self, holder, attempt_id, fake_stripe
    ) -> None:
        payment_intent_id = self.requires_action(holder, attempt_id, fake_stripe)
        hold = CardHold.objects.get()
        assert hold.status == CardHold.Status.PENDING and hold.target_document is None
        fake_stripe.set_status(payment_intent_id, "requires_capture")

        result = self.complete(holder, attempt_id, payment_intent_id)

        assert result.status == PlacementStatus.PLACED
        hold.refresh_from_db()
        assert hold.status == CardHold.Status.AUTHORIZED
        assert hold.target == result.target

    def test_a_payment_intent_that_isnt_this_attempt_is_refused_untouched(
        self, holder, attempt_id, fake_stripe
    ) -> None:
        payment_intent_id = self.requires_action(holder, attempt_id, fake_stripe)
        fake_stripe.set_status(payment_intent_id, "requires_capture")

        stranger = self.complete(UserFactory(), attempt_id, payment_intent_id)
        other_attempt = self.complete(holder, uuid.uuid4(), payment_intent_id)
        other_customer = self.complete(
            holder, attempt_id, payment_intent_id, stripe_customer_id="cus_other"
        )

        assert {stranger.status, other_attempt.status, other_customer.status} == {
            PlacementStatus.DECLINED
        }
        assert fake_stripe.calls_to("PaymentIntent.cancel") == []
        assert CardHold.objects.get().status == CardHold.Status.PENDING

    def test_failed_authentication_releases_the_hold(
        self, holder, attempt_id, fake_stripe, django_capture_on_commit_callbacks
    ) -> None:
        payment_intent_id = self.requires_action(holder, attempt_id, fake_stripe)
        fake_stripe.set_status(payment_intent_id, "requires_payment_method")

        with django_capture_on_commit_callbacks(execute=True):
            result = self.complete(holder, attempt_id, payment_intent_id)

        assert result.status == PlacementStatus.DECLINED
        assert CardHold.objects.get().status == CardHold.Status.RELEASED
        assert fake_stripe.status_of(payment_intent_id) == "canceled"

    def test_a_payment_intent_stripe_cant_find_declines(
        self, holder, attempt_id, fake_stripe
    ) -> None:
        assert self.complete(holder, attempt_id, "pi_missing").status == PlacementStatus.DECLINED

    def test_the_second_pass_needs_a_key_and_a_customer(
        self, holder, attempt_id, fake_stripe
    ) -> None:
        assert (
            self.complete(holder, attempt_id, "pi_x", stripe_customer_id="").status
            == PlacementStatus.DECLINED
        )

    def test_a_placed_attempt_returns_its_target(self, holder, attempt_id, fake_stripe) -> None:
        order = HoldableOrderFactory(user=holder)
        CardHoldFactory(target=order, attempt_id=attempt_id)

        result = self.complete(holder, attempt_id, "pi_anything")

        assert result.target == order
        assert fake_stripe.calls == []

    def test_a_failure_recording_the_hold_on_the_second_pass_cancels_it(
        self, holder, attempt_id, fake_stripe, django_capture_on_commit_callbacks
    ) -> None:
        """N2: as on the first pass, an authorization with no row is never left behind."""
        payment_intent_id = self.requires_action(holder, attempt_id, fake_stripe)
        CardHold.objects.all().delete()
        fake_stripe.set_status(payment_intent_id, "requires_capture")

        with (
            patch.object(holds, "record_pending_hold", side_effect=RuntimeError("db down")),
            django_capture_on_commit_callbacks(execute=True),
            pytest.raises(RuntimeError),
        ):
            self.complete(holder, attempt_id, payment_intent_id)

        hold = CardHold.objects.get()
        assert hold.status == CardHold.Status.RELEASED
        assert hold.release_reason == CardHold.ReleaseReason.ABANDONED
        assert fake_stripe.status_of(payment_intent_id) == "canceled"

    def test_an_unrecorded_payment_intent_is_recorded_from_stripe(
        self, holder, attempt_id, fake_stripe
    ) -> None:
        payment_intent_id = self.requires_action(holder, attempt_id, fake_stripe)
        CardHold.objects.all().delete()
        fake_stripe.set_status(payment_intent_id, "requires_capture")

        result = self.complete(holder, attempt_id, payment_intent_id)

        assert result.status == PlacementStatus.PLACED
        hold = CardHold.objects.get()
        assert hold.stripe_payment_method_id == "pm_visa" and hold.card_last4 == "4242"


class TestUnderTheLock:
    """Re-checks after authorization: every refusal releases the unlinked hold."""

    def authorized(self, holder, attempt_id, fake_stripe) -> str:
        fake_stripe.next_outcome = ["requires_action"]
        place(holder, new_order(holder), attempt_id)
        (payment_intent_id,) = fake_stripe.intents
        fake_stripe.set_status(payment_intent_id, "requires_capture")
        return payment_intent_id

    def complete(
        self, holder, attempt_id, payment_intent_id, link, expected=10_000
    ) -> PlacementResult:
        return complete_on_session(
            payment_intent_id,
            link,
            user=holder,
            attempt_id=attempt_id,
            stripe_customer_id=STRIPE_CUSTOMER_ID,
            expected_amount_cents=expected,
        )

    def test_a_refusal_rolls_back_the_target_and_releases_the_hold(
        self, holder, attempt_id, fake_stripe, django_capture_on_commit_callbacks
    ) -> None:
        payment_intent_id = self.authorized(holder, attempt_id, fake_stripe)
        released = []
        card_hold_released.connect(
            lambda **kwargs: released.append(kwargs["hold_id"]), weak=False, dispatch_uid="t-rel"
        )

        def link(hold) -> HoldableOrder:
            HoldableOrderFactory(user=holder)
            raise HoldRefused({"field": "slot", "message": "full"})

        try:
            with django_capture_on_commit_callbacks(execute=True):
                result = self.complete(holder, attempt_id, payment_intent_id, link)
        finally:
            card_hold_released.disconnect(dispatch_uid="t-rel")

        assert result.status == PlacementStatus.REFUSED
        assert result.errors == {"field": "slot", "message": "full"}
        assert not HoldableOrder.objects.exists()
        hold = CardHold.objects.get()
        assert hold.status == CardHold.Status.RELEASED
        assert released == [hold.pk]
        assert fake_stripe.status_of(payment_intent_id) == "canceled"

    def test_the_target_is_re_priced_under_the_lock(
        self, holder, attempt_id, fake_stripe, django_capture_on_commit_callbacks
    ) -> None:
        payment_intent_id = self.authorized(holder, attempt_id, fake_stripe)

        with django_capture_on_commit_callbacks(execute=True):
            result = self.complete(
                holder, attempt_id, payment_intent_id, saving(new_order(holder, 12_000))
            )

        assert result.status == PlacementStatus.AMOUNT_CHANGED
        assert not HoldableOrder.objects.exists()
        assert CardHold.objects.get().status == CardHold.Status.RELEASED
        assert fake_stripe.status_of(payment_intent_id) == "canceled"

    def test_the_payment_intent_must_carry_the_hold_amount(
        self, holder, attempt_id, fake_stripe
    ) -> None:
        payment_intent_id = self.authorized(holder, attempt_id, fake_stripe)
        # Same estimate, but the buffer changed since the authorization.
        order = new_order(holder, buffer_percent=Decimal("20"))

        result = self.complete(holder, attempt_id, payment_intent_id, saving(order))

        assert result.status == PlacementStatus.AMOUNT_CHANGED

    def test_a_target_of_someone_else_is_refused(self, holder, attempt_id, fake_stripe) -> None:
        payment_intent_id = self.authorized(holder, attempt_id, fake_stripe)

        result = self.complete(
            holder, attempt_id, payment_intent_id, saving(new_order(UserFactory()))
        )

        assert result.status == PlacementStatus.REFUSED
        assert CardHold.objects.get().status == CardHold.Status.RELEASED

    def test_link_must_return_a_saved_target(self, holder, attempt_id, fake_stripe) -> None:
        payment_intent_id = self.authorized(holder, attempt_id, fake_stripe)

        result = self.complete(holder, attempt_id, payment_intent_id, lambda hold: None)

        assert result.status == PlacementStatus.REFUSED

    def test_a_target_with_a_hold_already_is_refused(self, holder, attempt_id, fake_stripe) -> None:
        payment_intent_id = self.authorized(holder, attempt_id, fake_stripe)
        order = HoldableOrderFactory(user=holder)
        CardHoldFactory(target=order, status=CardHold.Status.RELEASED)

        result = self.complete(holder, attempt_id, payment_intent_id, lambda hold: order)

        assert result.status == PlacementStatus.REFUSED

    def test_a_concurrent_link_of_the_same_target_is_refused_not_raised(
        self, holder, attempt_id, fake_stripe, django_capture_on_commit_callbacks
    ) -> None:
        """m8: two placements whose ``link`` returns the same existing target, unlocked.
        The other one links first, after this one looked for a previous hold: the
        one-to-one answers, as a refusal."""
        payment_intent_id = self.authorized(holder, attempt_id, fake_stripe)
        order = HoldableOrderFactory(user=holder)
        expiry = holds.hold_expiry

        def linked_meanwhile(payment_intent: Any) -> Any:
            CardHoldFactory(target=order)
            return expiry(payment_intent)

        with (
            patch.object(holds, "hold_expiry", side_effect=linked_meanwhile),
            django_capture_on_commit_callbacks(execute=True),
        ):
            result = self.complete(holder, attempt_id, payment_intent_id, lambda hold: order)

        assert result.status == PlacementStatus.REFUSED
        hold = CardHold.objects.get(stripe_payment_intent_id=payment_intent_id)
        assert hold.status == CardHold.Status.RELEASED and hold.target_document_id is None
        assert fake_stripe.status_of(payment_intent_id) == "canceled"

    def test_an_exception_releases_the_hold_and_is_raised(
        self, holder, attempt_id, fake_stripe, django_capture_on_commit_callbacks
    ) -> None:
        payment_intent_id = self.authorized(holder, attempt_id, fake_stripe)

        def link(hold) -> HoldableOrder:
            raise RuntimeError("boom")

        with django_capture_on_commit_callbacks(execute=True), pytest.raises(RuntimeError):
            self.complete(holder, attempt_id, payment_intent_id, link)

        assert CardHold.objects.get().status == CardHold.Status.RELEASED
        assert fake_stripe.status_of(payment_intent_id) == "canceled"

    def test_a_hold_linked_meanwhile_returns_its_target_and_is_never_cancelled(
        self, holder, attempt_id, fake_stripe, django_capture_on_commit_callbacks
    ) -> None:
        payment_intent_id = self.authorized(holder, attempt_id, fake_stripe)
        order = HoldableOrderFactory(user=holder)
        CardHold.objects.filter(stripe_payment_intent_id=payment_intent_id).update(
            target_document=DocumentId.get_or_create_for_object(order),
            status=CardHold.Status.AUTHORIZED,
        )

        with django_capture_on_commit_callbacks(execute=True):
            # Through _complete directly: find_placed would short-circuit first.
            result = holds._complete(
                payment_intent=holds.retrieve_payment_intent(payment_intent_id),
                link=lambda hold: pytest.fail("linked twice"),
                target=None,
                expected_amount_cents=10_000,
            )

        assert result.status == PlacementStatus.PLACED
        assert result.target == order
        assert fake_stripe.calls_to("PaymentIntent.cancel") == []

    def test_only_pending_holds_are_linked(
        self, holder, attempt_id, fake_stripe, django_capture_on_commit_callbacks
    ) -> None:
        payment_intent_id = self.authorized(holder, attempt_id, fake_stripe)
        CardHold.objects.update(status=CardHold.Status.RELEASED)  # the sweep claimed it

        with django_capture_on_commit_callbacks(execute=True):
            result = self.complete(holder, attempt_id, payment_intent_id, saving(new_order(holder)))

        assert result.status == PlacementStatus.DECLINED
        assert not HoldableOrder.objects.exists()


class TestExistingTarget:
    def test_holding_a_saved_target_locks_it_before_the_hold(
        self, holder, attempt_id, fake_stripe
    ) -> None:
        order = HoldableOrderFactory(user=holder)

        with CaptureQueriesContext(connection) as queries:
            result = place(holder, order, attempt_id)

        assert result.status == PlacementStatus.PLACED
        assert CardHold.objects.get().target == order
        locks = [
            query["sql"]
            for query in queries.captured_queries
            if "FOR UPDATE" in query["sql"]
            and ("testapp_holdableorder" in query["sql"] or "payments_cardhold" in query["sql"])
        ]
        assert "testapp_holdableorder" in locks[0]
        assert "payments_cardhold" in locks[1]

    def test_the_lock_hook_is_called(self, holder, attempt_id, fake_stripe) -> None:
        order = HoldableOrderFactory(user=holder)
        HoldableOrderHoldTarget.lock_log = []
        try:
            place(holder, order, attempt_id)
            assert HoldableOrderHoldTarget.lock_log == ["target"]
        finally:
            HoldableOrderHoldTarget.lock_log = None


class TestAbandon:
    def test_without_a_row_or_user_the_cancel_is_direct(
        self, fake_stripe, django_capture_on_commit_callbacks
    ) -> None:
        fake_stripe.intents["pi_loose"] = {
            "id": "pi_loose",
            "object": "payment_intent",
            "status": "requires_capture",
            "amount": 1,
            "payment_method": "pm_visa",
            "capture_before": None,
        }

        with django_capture_on_commit_callbacks(execute=True):
            abandon_hold("pi_loose")

        assert fake_stripe.status_of("pi_loose") == "canceled"
        assert not CardHold.objects.exists()

    def test_a_failing_direct_cancel_is_logged(
        self, fake_stripe, django_capture_on_commit_callbacks, caplog
    ) -> None:
        with django_capture_on_commit_callbacks(execute=True):
            abandon_hold("pi_unknown")

        assert "Could not cancel PaymentIntent pi_unknown" in caplog.text

    def test_a_linked_hold_is_never_abandoned(self, holder, fake_stripe) -> None:
        hold = CardHoldFactory(target=HoldableOrderFactory(user=holder))

        abandon_hold(hold.stripe_payment_intent_id)

        hold.refresh_from_db()
        assert hold.status == CardHold.Status.AUTHORIZED

    def test_nothing_to_abandon(self, fake_stripe) -> None:
        abandon_hold(None)
        assert fake_stripe.calls == []

    def test_a_row_that_cant_be_written_still_cancels(
        self, holder, fake_stripe, django_capture_on_commit_callbacks, caplog
    ) -> None:
        fake_stripe.intents["pi_loose"] = {
            "id": "pi_loose",
            "status": "requires_capture",
            "amount": 1,
            "payment_method": "pm_visa",
            "capture_before": None,
        }
        with (
            patch.object(CardHold.objects, "create", side_effect=RuntimeError("db")),
            django_capture_on_commit_callbacks(execute=True),
        ):
            abandon_hold("pi_loose", user=holder, attempt_id=uuid.uuid4())

        assert fake_stripe.status_of("pi_loose") == "canceled"
        assert "Could not record released PaymentIntent pi_loose" in caplog.text


def test_stripe_errors_have_the_codes_the_service_reads() -> None:
    assert getattr(concurrent_request(), "http_status") == 409
    assert isinstance(connection_error(), stripe.APIConnectionError)
