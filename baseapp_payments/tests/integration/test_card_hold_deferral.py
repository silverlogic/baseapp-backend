"""Holds placed later, without the customer present (CARD_HOLDS_DEFERRAL_ENABLED): the
scheduled first pass, the sweep's off-session placement, failures, staff decisions,
rescheduling and releasing before placement. Stripe is the in-memory ``FakeStripe``."""

import datetime
import uuid
from collections.abc import Generator
from typing import Any
from unittest.mock import Mock, patch

import pytest
import stripe
import swapper
from constance.test import override_config
from django.utils import timezone

from baseapp_payments import holds, tasks
from baseapp_payments.holds import (
    CaptureStatus,
    HoldRefused,
    PlacementResult,
    PlacementStatus,
    authorize_on_session,
    cancel_failed_hold,
    capture,
    card_in_use,
    complete_setup_on_session,
    find_attempt,
    keep_failed_hold,
    place_scheduled,
    release,
    release_for_charge,
    release_target_holds_on_commit,
    reschedule,
    reschedule_hold,
    reschedule_on_commit,
    scheduled_idempotency_key,
)
from baseapp_payments.signals import card_hold_authorized, card_hold_failed
from baseapp_payments.tasks import reschedule_card_hold, sweep_card_holds
from testproject.testapp.card_holds import HoldableOrderHoldTarget
from testproject.testapp.models import HoldableOrder

from ..factories import CardHoldFactory, HoldableOrderFactory, UserFactory
from ..fakes import (
    CAPTURE_BEFORE,
    STRIPE_CUSTOMER_ID,
    api_error,
    connection_error,
    rate_limited,
    unexpected_state,
)
from ..helpers import grant_card_hold_perm

CardHold = swapper.load_model("baseapp_payments", "CardHold")

pytestmark = pytest.mark.django_db


@pytest.fixture
def deferral() -> Generator[None, None, None]:
    with override_config(CARD_HOLDS_DEFERRAL_ENABLED=True):
        yield


@pytest.fixture
def eager_retries() -> Generator[None, None, None]:
    """Run Celery's eager retries through to the end instead of raising ``Retry``."""
    conf = reschedule_card_hold._get_app().conf
    keys = ("task_eager_propagates", "CELERY_TASK_EAGER_PROPAGATES")
    before = {key: conf.get(key) for key in keys}
    conf.update({key: False for key in keys})
    yield
    conf.update(before)


def today() -> datetime.date:
    return timezone.localdate()


def days(count: int) -> datetime.date:
    return today() + datetime.timedelta(days=count)


def place(holder, order: HoldableOrder, attempt_id=None, **kwargs) -> PlacementResult:
    """The first pass, as a project's create mutation calls it."""
    kwargs.setdefault("payment_method_id", "pm_visa")
    kwargs.setdefault("expected_amount_cents", order.amount_cents)
    link = kwargs.pop("link", None)
    if link is None and order.pk is None:

        def link(hold) -> HoldableOrder:
            order.save()
            return order

    return authorize_on_session(
        user=holder,
        attempt_id=attempt_id or uuid.uuid4(),
        stripe_customer_id=STRIPE_CUSTOMER_ID,
        target=order,
        link=link,
        **kwargs,
    )


def scheduled(holder, target_date: datetime.date | None = None, **fields) -> Any:
    """A hold as scheduling leaves it, on a saved order of ``holder``."""
    order = HoldableOrderFactory(user=holder, target_date=target_date or days(30))
    hold_on = fields.pop("hold_on", order.target_date - datetime.timedelta(days=4))
    fields.setdefault("status", CardHold.Status.SCHEDULED)
    return CardHoldFactory(
        target=order,
        stripe_payment_intent_id=None,
        expires_at=None,
        hold_on=hold_on,
        **fields,
    )


def due(holder, **fields) -> Any:
    """A scheduled hold whose day is today."""
    return scheduled(holder, target_date=days(4), hold_on=today(), **fields)


def reload(hold) -> Any:
    hold.refresh_from_db()
    return hold


def creates(fake_stripe) -> list[dict]:
    return [params for _args, params in fake_stripe.calls_to("PaymentIntent.create")]


class Listener:
    """Collects a signal's sends for the duration of a test."""

    def __init__(self, signal) -> None:
        self.signal = signal
        self.sent: list[dict] = []
        self.uid = f"test-{id(self)}"
        signal.connect(self.receive, weak=False, dispatch_uid=self.uid)

    def receive(self, **kwargs) -> None:
        self.sent.append(kwargs)

    def close(self) -> None:
        self.signal.disconnect(dispatch_uid=self.uid)


@pytest.fixture
def failed_signal() -> Generator[Listener, None, None]:
    listener = Listener(card_hold_failed)
    yield listener
    listener.close()


@pytest.fixture
def staff_member(db) -> Any:
    return grant_card_hold_perm(UserFactory(is_staff=True, email="ops@example.com"))


# --- 1. Placement ---------------------------------------------------------------------


class TestFirstPass:
    def test_without_deferral_a_far_target_is_held_now_as_before(self, holder, fake_stripe) -> None:
        order = HoldableOrder(user=holder, amount_cents=10_000, target_date=days(30))

        result = place(holder, order)

        assert result.status == PlacementStatus.PLACED
        assert CardHold.objects.get().status == CardHold.Status.AUTHORIZED
        assert fake_stripe.calls_to("SetupIntent.create") == []

    @pytest.mark.parametrize("target_date", [1, 3, 4])
    def test_a_target_inside_the_window_is_held_now(
        self, holder, fake_stripe, deferral, target_date
    ) -> None:
        order = HoldableOrder(user=holder, amount_cents=10_000, target_date=days(target_date))

        result = place(holder, order)

        assert result.status == PlacementStatus.PLACED
        assert len(creates(fake_stripe)) == 1
        assert "off_session" not in creates(fake_stripe)[0]

    def test_a_far_target_is_scheduled_and_nothing_is_authorized(
        self, holder, fake_stripe, deferral
    ) -> None:
        fake_stripe.add_card("pm_new", customer=None)
        order = HoldableOrder(user=holder, amount_cents=10_000, target_date=days(30))
        attempt_id = uuid.uuid4()

        result = place(holder, order, attempt_id, payment_method_id="pm_new")

        assert result.status == PlacementStatus.SCHEDULED
        assert result.target == order and order.pk is not None
        assert result.hold_on == days(26)
        assert creates(fake_stripe) == []
        ((_args, params),) = fake_stripe.calls_to("SetupIntent.create")
        assert params["usage"] == "off_session"
        assert params["customer"] == STRIPE_CUSTOMER_ID
        assert params["payment_method"] == "pm_new"
        assert params["idempotency_key"] == f"testproject-setup-{holder.pk}-{attempt_id}"
        assert fake_stripe.payment_methods["pm_new"]["customer"] == STRIPE_CUSTOMER_ID
        hold = CardHold.objects.get()
        assert hold.status == CardHold.Status.SCHEDULED
        assert hold.target == order
        assert hold.hold_on == days(26)
        assert hold.stripe_payment_intent_id is None
        (setup_intent_id,) = fake_stripe.setup_intents
        assert hold.stripe_setup_intent_id == setup_intent_id
        assert hold.stripe_payment_method_id == "pm_new"
        assert (hold.card_brand, hold.card_last4) == ("visa", "4242")
        assert (hold.estimated_amount_cents, hold.amount_cents) == (10_000, 11_000)
        assert hold.expires_at is None

    def test_the_scheduled_card_is_in_use(self, holder, fake_stripe, deferral) -> None:
        place(holder, HoldableOrder(user=holder, target_date=days(30)))

        assert card_in_use(holder, "pm_visa")

    def test_a_retry_answers_scheduled_from_the_database(
        self, holder, fake_stripe, deferral
    ) -> None:
        attempt_id = uuid.uuid4()
        first = place(holder, HoldableOrder(user=holder, target_date=days(30)), attempt_id)
        calls = len(fake_stripe.calls)

        again = place(holder, HoldableOrder(user=holder, target_date=days(30)), attempt_id)

        assert again.status == PlacementStatus.SCHEDULED
        assert again.target == first.target and again.hold_on == days(26)
        assert len(fake_stripe.calls) == calls
        assert HoldableOrder.objects.count() == 1

    def test_a_failed_hold_answers_scheduled_to_its_customer(self, holder) -> None:
        hold = due(holder, status=CardHold.Status.FAILED)

        found = find_attempt(holder, hold.attempt_id)

        assert found.status == PlacementStatus.SCHEDULED

    @pytest.mark.parametrize("window, held_on", [(2, 28), (5, 26), (9, 26), (0, 29)])
    def test_the_adapter_window_is_clamped(
        self, holder, fake_stripe, deferral, window, held_on
    ) -> None:
        with patch.object(HoldableOrderHoldTarget, "window_days", return_value=window):
            result = place(holder, HoldableOrder(user=holder, target_date=days(30)))

        assert result.hold_on == days(held_on)

    def test_the_constance_window_moves_the_day(self, holder, fake_stripe) -> None:
        with override_config(CARD_HOLDS_DEFERRAL_ENABLED=True, CARD_HOLDS_WINDOW_DAYS=3):
            result = place(holder, HoldableOrder(user=holder, target_date=days(30)))

        assert result.hold_on == days(27)

    def test_a_refusal_by_link_keeps_nothing_and_calls_no_cancel(
        self, holder, fake_stripe, deferral, django_capture_on_commit_callbacks
    ) -> None:
        def refuse(hold) -> HoldableOrder:
            raise HoldRefused(["full"])

        with django_capture_on_commit_callbacks(execute=True):
            result = place(holder, HoldableOrder(user=holder, target_date=days(30)), link=refuse)

        assert result.status == PlacementStatus.REFUSED and result.errors == ["full"]
        hold = CardHold.objects.get()
        assert hold.status == CardHold.Status.RELEASED
        assert hold.release_reason == CardHold.ReleaseReason.ABANDONED
        assert hold.release_confirmed_at is not None
        assert fake_stripe.calls_to("PaymentIntent.cancel") == []

    def test_a_price_change_under_the_lock_schedules_nothing(
        self, holder, fake_stripe, deferral
    ) -> None:
        order = HoldableOrder(user=holder, amount_cents=10_000, target_date=days(30))

        def reprice(hold) -> HoldableOrder:
            order.amount_cents = 12_000
            order.save()
            return order

        result = place(holder, order, link=reprice)

        assert result.status == PlacementStatus.AMOUNT_CHANGED
        assert CardHold.objects.get().status == CardHold.Status.RELEASED

    def test_an_existing_targets_released_hold_is_re_armed_scheduled(
        self, holder, fake_stripe, deferral
    ) -> None:
        order = HoldableOrderFactory(user=holder, target_date=days(30))
        previous = CardHoldFactory(
            target=order, status=CardHold.Status.RELEASED, stripe_payment_intent_id="pi_old"
        )

        result = place(holder, order)

        assert result.status == PlacementStatus.SCHEDULED
        hold = reload(previous)
        assert hold.status == CardHold.Status.SCHEDULED
        assert hold.stripe_payment_intent_id is None
        assert hold.previous_payment_intent_ids == ["pi_old"]
        assert hold.stripe_setup_intent_id and hold.hold_on == days(26)
        assert CardHold.objects.count() == 1

    @pytest.mark.parametrize("outcome", ["card_declined", "requires_payment_method"])
    def test_a_card_that_cant_be_saved_declines(
        self, holder, fake_stripe, deferral, outcome
    ) -> None:
        fake_stripe.next_setup_outcome = [outcome]

        result = place(holder, HoldableOrder(user=holder, target_date=days(30)))

        assert result.status == PlacementStatus.DECLINED
        assert not HoldableOrder.objects.exists()

    def test_no_usable_answer_saving_the_card_is_in_progress(
        self, holder, fake_stripe, deferral
    ) -> None:
        fake_stripe.fail_next("SetupIntent.create", connection_error())
        fake_stripe.fail_next("SetupIntent.create", rate_limited())

        result = place(holder, HoldableOrder(user=holder, target_date=days(30)))

        assert result.status == PlacementStatus.IN_PROGRESS
        assert len(fake_stripe.calls_to("SetupIntent.create")) == 2

    def test_a_replayed_setup_intent_is_re_read(self, holder, fake_stripe, deferral) -> None:
        attempt_id = uuid.uuid4()
        fake_stripe.next_setup_outcome = ["requires_action"]
        assert (
            place(holder, HoldableOrder(user=holder, target_date=days(30)), attempt_id).status
            == PlacementStatus.REQUIRES_ACTION
        )
        (setup_intent_id,) = fake_stripe.setup_intents
        fake_stripe.attach(setup_intent_id)

        # The client retried the first pass instead of sending the second: the replay
        # reads the SetupIntent's live state (succeeded) and schedules.
        result = place(holder, HoldableOrder(user=holder, target_date=days(30)), attempt_id)

        assert result.status == PlacementStatus.SCHEDULED
        assert fake_stripe.calls_to("SetupIntent.retrieve")


class TestSetupSecondPass:
    def first_pass(self, holder, fake_stripe, attempt_id) -> str:
        fake_stripe.next_setup_outcome = ["requires_action"]
        result = place(holder, HoldableOrder(user=holder, target_date=days(30)), attempt_id)
        assert result.status == PlacementStatus.REQUIRES_ACTION
        assert result.intent_type == "setup_intent"
        (setup_intent_id,) = fake_stripe.setup_intents
        assert result.client_secret == f"{setup_intent_id}_secret"
        assert CardHold.objects.get().status == CardHold.Status.PENDING
        return setup_intent_id

    def second_pass(
        self, holder, attempt_id, setup_intent_id, order=None, **kwargs
    ) -> PlacementResult:
        order = order or HoldableOrder(user=holder, target_date=days(30))

        def link(hold) -> HoldableOrder:
            order.save()
            return order

        return complete_setup_on_session(
            setup_intent_id,
            link,
            user=holder,
            attempt_id=attempt_id,
            stripe_customer_id=STRIPE_CUSTOMER_ID,
            expected_amount_cents=order.amount_cents,
            **kwargs,
        )

    def test_after_authentication_the_hold_is_scheduled(
        self, holder, fake_stripe, deferral
    ) -> None:
        attempt_id = uuid.uuid4()
        setup_intent_id = self.first_pass(holder, fake_stripe, attempt_id)
        fake_stripe.attach(setup_intent_id)

        result = self.second_pass(holder, attempt_id, setup_intent_id)

        assert result.status == PlacementStatus.SCHEDULED
        hold = CardHold.objects.get()
        assert hold.status == CardHold.Status.SCHEDULED and hold.target == result.target
        assert creates(fake_stripe) == []

    def test_a_second_pass_whose_day_has_come_places_at_once(
        self, holder, fake_stripe, deferral
    ) -> None:
        attempt_id = uuid.uuid4()
        setup_intent_id = self.first_pass(holder, fake_stripe, attempt_id)
        fake_stripe.attach(setup_intent_id)

        # The date moved into the window while the customer authenticated.
        order = HoldableOrder(user=holder, target_date=days(2))
        result = self.second_pass(holder, attempt_id, setup_intent_id, order=order)

        assert result.status == PlacementStatus.PLACED
        assert result.target == order
        (params,) = creates(fake_stripe)
        assert params["off_session"] is True
        assert CardHold.objects.get().status == CardHold.Status.AUTHORIZED

    def test_one_that_fails_at_once_reads_scheduled(
        self, holder, fake_stripe, deferral, failed_signal, django_capture_on_commit_callbacks
    ) -> None:
        attempt_id = uuid.uuid4()
        setup_intent_id = self.first_pass(holder, fake_stripe, attempt_id)
        fake_stripe.attach(setup_intent_id)
        fake_stripe.next_outcome = ["card_declined"]

        with django_capture_on_commit_callbacks(execute=True):
            result = self.second_pass(
                holder, attempt_id, setup_intent_id, order=HoldableOrder(user=holder)
            )

        assert result.status == PlacementStatus.SCHEDULED
        assert CardHold.objects.get().status == CardHold.Status.FAILED
        assert len(failed_signal.sent) == 1

    def test_a_setup_intent_still_waiting_is_in_progress(
        self, holder, fake_stripe, deferral
    ) -> None:
        attempt_id = uuid.uuid4()
        setup_intent_id = self.first_pass(holder, fake_stripe, attempt_id)

        result = self.second_pass(holder, attempt_id, setup_intent_id)

        assert result.status == PlacementStatus.IN_PROGRESS
        assert not HoldableOrder.objects.exists()

    def test_a_setup_intent_that_saved_nothing_declines_and_is_released(
        self, holder, fake_stripe, deferral
    ) -> None:
        attempt_id = uuid.uuid4()
        setup_intent_id = self.first_pass(holder, fake_stripe, attempt_id)
        fake_stripe.setup_intents[setup_intent_id]["status"] = "requires_payment_method"

        result = self.second_pass(holder, attempt_id, setup_intent_id)

        assert result.status == PlacementStatus.DECLINED
        hold = CardHold.objects.get()
        assert hold.status == CardHold.Status.RELEASED and hold.release_confirmed_at
        assert find_attempt(holder, attempt_id).status == PlacementStatus.DECLINED

    def test_someone_elses_setup_intent_is_refused_untouched(
        self, holder, fake_stripe, deferral
    ) -> None:
        attempt_id = uuid.uuid4()
        setup_intent_id = self.first_pass(holder, fake_stripe, attempt_id)
        fake_stripe.attach(setup_intent_id)
        other = UserFactory()

        result = self.second_pass(other, uuid.uuid4(), setup_intent_id)

        assert result.status == PlacementStatus.DECLINED
        assert CardHold.objects.get().status == CardHold.Status.PENDING

    def test_an_unknown_setup_intent_declines(self, holder, fake_stripe, deferral) -> None:
        assert self.second_pass(holder, uuid.uuid4(), "seti_nope").status == (
            PlacementStatus.DECLINED
        )

    def test_a_link_that_raises_releases_the_saved_card_row(
        self, holder, fake_stripe, deferral
    ) -> None:
        attempt_id = uuid.uuid4()
        setup_intent_id = self.first_pass(holder, fake_stripe, attempt_id)
        fake_stripe.attach(setup_intent_id)

        def boom(hold) -> HoldableOrder:
            raise RuntimeError("boom")

        with pytest.raises(RuntimeError):
            complete_setup_on_session(
                setup_intent_id,
                boom,
                user=holder,
                attempt_id=attempt_id,
                stripe_customer_id=STRIPE_CUSTOMER_ID,
            )

        assert CardHold.objects.get().status == CardHold.Status.RELEASED


# --- 2-3. The sweep's off-session placement -------------------------------------------


class TestPlacingAheadOfTheDate:
    def test_the_sweep_places_a_due_hold_off_session_at_the_current_price(
        self, holder, fake_stripe, deferral, django_capture_on_commit_callbacks
    ) -> None:
        hold = due(holder)
        HoldableOrder.objects.filter(pk=hold.target.pk).update(amount_cents=20_000)
        authorized = Listener(card_hold_authorized)
        try:
            with django_capture_on_commit_callbacks(execute=True):
                sweep_card_holds()
        finally:
            authorized.close()

        (params,) = creates(fake_stripe)
        assert params["off_session"] is True and params["confirm"] is True
        assert params["capture_method"] == "manual"
        assert params["payment_method"] == "pm_visa"
        assert params["customer"] == STRIPE_CUSTOMER_ID
        assert params["amount"] == 22_000
        assert params["idempotency_key"] == (
            f"testproject-hold-scheduled-{hold.pk}-{hold.attempt_id}-0"
        )
        hold = reload(hold)
        assert hold.status == CardHold.Status.AUTHORIZED
        (payment_intent_id,) = fake_stripe.intents
        assert hold.stripe_payment_intent_id == payment_intent_id
        assert (hold.estimated_amount_cents, hold.amount_cents) == (20_000, 22_000)
        assert hold.expires_at == datetime.datetime.fromtimestamp(
            CAPTURE_BEFORE, tz=datetime.timezone.utc
        )
        assert hold.placement_key == "" and hold.placement_claimed_at is None
        assert authorized.sent[0]["hold"] == hold

    def test_without_capture_before_an_off_session_hold_assumes_4_days_18_hours(
        self, holder, fake_stripe, deferral, caplog
    ) -> None:
        hold = due(holder)
        fake_stripe.capture_before = None

        before = timezone.now()
        assert place_scheduled(hold.pk).status == PlacementStatus.PLACED

        expires = reload(hold).expires_at - before
        window = datetime.timedelta(days=4, hours=18)
        assert window <= expires < window + datetime.timedelta(minutes=1)
        assert "assuming a hold of 4 days, 18:00:00" in caplog.text

    def test_a_hold_whose_day_hasnt_come_waits(self, holder, fake_stripe, deferral) -> None:
        hold = scheduled(holder)

        sweep_card_holds()
        assert place_scheduled(hold.pk).status == PlacementStatus.SCHEDULED

        assert creates(fake_stripe) == []
        assert reload(hold).status == CardHold.Status.SCHEDULED

    def test_a_target_outside_filter_holdable_isnt_placed(
        self, holder, fake_stripe, deferral
    ) -> None:
        hold = due(holder)
        with patch.object(
            HoldableOrderHoldTarget, "filter_holdable", lambda self, queryset: queryset.none()
        ):
            sweep_card_holds()
            assert place_scheduled(hold.pk).status == PlacementStatus.REFUSED

        assert creates(fake_stripe) == []
        assert reload(hold).status == CardHold.Status.SCHEDULED

    def test_without_deferral_the_sweep_places_nothing(self, holder, fake_stripe) -> None:
        due(holder)

        sweep_card_holds()

        assert creates(fake_stripe) == []

    @pytest.mark.parametrize("status", ["cancelled", "charged"])
    def test_a_target_done_with_meanwhile_is_released_without_stripe(
        self, holder, fake_stripe, deferral, status
    ) -> None:
        hold = due(holder)
        HoldableOrder.objects.filter(pk=hold.target.pk).update(status=status)

        assert place_scheduled(hold.pk).status == PlacementStatus.REFUSED

        hold = reload(hold)
        assert hold.status == CardHold.Status.RELEASED
        assert hold.release_reason == ("cancelled" if status == "cancelled" else "card_released")
        assert hold.release_confirmed_at is not None
        assert fake_stripe.calls == []

    def test_a_live_claim_answers_in_progress_and_calls_nothing(
        self, holder, fake_stripe, deferral
    ) -> None:
        hold = due(holder, placement_claimed_at=timezone.now())

        assert place_scheduled(hold.pk).status == PlacementStatus.IN_PROGRESS
        sweep_card_holds()

        assert fake_stripe.calls == []

    def test_a_stale_claim_is_taken_over(self, holder, fake_stripe, deferral) -> None:
        hold = due(holder, placement_claimed_at=timezone.now() - datetime.timedelta(hours=1))

        sweep_card_holds()

        assert reload(hold).status == CardHold.Status.AUTHORIZED

    def test_a_redelivered_task_places_once(self, holder, fake_stripe, deferral) -> None:
        hold = due(holder)

        tasks.place_card_hold(hold.pk)
        tasks.place_card_hold(hold.pk)

        assert len(creates(fake_stripe)) == 1

    def test_nothing_to_hold_fails(self, holder, fake_stripe, deferral) -> None:
        hold = due(holder)
        HoldableOrder.objects.filter(pk=hold.target.pk).update(amount_cents=0)

        assert place_scheduled(hold.pk).status == PlacementStatus.DECLINED

        assert reload(hold).failure_code == "nothing_to_hold"
        assert fake_stripe.calls == []

    def test_without_stripe_or_a_scheduled_row_nothing_happens(
        self, holder, fake_stripe, deferral, settings
    ) -> None:
        hold = due(holder)
        assert place_scheduled(CardHoldFactory(customer=holder).pk) is None
        settings.STRIPE_SECRET_KEY = ""

        assert place_scheduled(hold.pk) is None
        assert fake_stripe.calls == []


class TestAFailedHoldIsFinal:
    @pytest.mark.parametrize(
        "outcome, code",
        [
            ("card_declined", "card_declined"),
            ("insufficient_funds", "insufficient_funds"),
            ("authentication_required", "authentication_required"),
        ],
    )
    def test_a_decline_fails_the_hold_and_tells_staff_not_the_customer(
        self,
        holder,
        fake_stripe,
        deferral,
        failed_signal,
        staff_member,
        mailoutbox,
        django_capture_on_commit_callbacks,
        outcome,
        code,
    ) -> None:
        hold = due(holder)
        fake_stripe.next_outcome = [outcome]

        with django_capture_on_commit_callbacks(execute=True):
            result = place_scheduled(hold.pk)

        assert result.status == PlacementStatus.DECLINED
        hold = reload(hold)
        assert hold.status == CardHold.Status.FAILED
        assert hold.failure_code == code and hold.failed_at is not None
        assert hold.stripe_payment_intent_id  # the failed PaymentIntent, for staff
        assert failed_signal.sent[0]["hold"] == hold
        assert failed_signal.sent[0]["target"] == hold.target
        (mail,) = mailoutbox
        assert mail.to == ["ops@example.com"]
        assert holder.email not in mail.to
        assert str(hold.target) in mail.subject
        assert code in mail.body and holder.email in mail.body
        assert hold.target.target_date.isoformat() in mail.body

    def test_a_failed_hold_is_never_retried(self, holder, fake_stripe, deferral) -> None:
        hold = due(holder)
        fake_stripe.next_outcome = ["card_declined"]
        place_scheduled(hold.pk)

        sweep_card_holds()
        assert place_scheduled(hold.pk) is None

        assert len(creates(fake_stripe)) == 1

    def test_a_non_retryable_stripe_error_fails(self, holder, fake_stripe, deferral) -> None:
        hold = due(holder)
        fake_stripe.fail_next(
            "PaymentIntent.create",
            stripe.InvalidRequestError("No such PaymentMethod", "payment_method", code="x_gone"),
        )

        assert place_scheduled(hold.pk).status == PlacementStatus.DECLINED

        assert reload(hold).failure_code == "x_gone"

    def test_a_reused_key_with_other_parameters_fails(self, holder, fake_stripe, deferral) -> None:
        hold = due(holder)
        fake_stripe.fail_next("PaymentIntent.create", stripe.IdempotencyError("reused"))

        assert place_scheduled(hold.pk).status == PlacementStatus.DECLINED
        assert reload(hold).failure_code == "IdempotencyError"

    def test_a_payment_intent_wanting_authentication_fails_and_is_cancelled(
        self, holder, fake_stripe, deferral, django_capture_on_commit_callbacks
    ) -> None:
        hold = due(holder)
        fake_stripe.next_outcome = ["requires_action"]

        with django_capture_on_commit_callbacks(execute=True):
            place_scheduled(hold.pk)

        hold = reload(hold)
        assert hold.failure_code == "authentication_required"
        assert fake_stripe.status_of(hold.stripe_payment_intent_id) == "canceled"

    def test_an_unexpected_status_fails_with_it(self, holder, fake_stripe, deferral) -> None:
        hold = due(holder)
        fake_stripe.next_outcome = ["canceled"]

        place_scheduled(hold.pk)

        assert reload(hold).failure_code == "canceled"

    @pytest.mark.parametrize(
        "error", [connection_error, api_error, rate_limited], ids=["conn", "5xx", "429"]
    )
    def test_no_usable_answer_leaves_it_scheduled_for_the_next_sweep(
        self, holder, fake_stripe, deferral, failed_signal, error
    ) -> None:
        hold = due(holder)
        fake_stripe.fail_next("PaymentIntent.create", error())

        assert place_scheduled(hold.pk).status == PlacementStatus.IN_PROGRESS

        hold = reload(hold)
        assert hold.status == CardHold.Status.SCHEDULED
        key = hold.placement_key
        assert key and hold.placement_amount_cents == 11_000
        assert hold.placement_claimed_at is None
        assert failed_signal.sent == []
        # The price changes, but the retry must send what the key was first sent with.
        HoldableOrder.objects.filter(pk=hold.target.pk).update(amount_cents=50_000)

        sweep_card_holds()

        first, second = creates(fake_stripe)
        assert first["idempotency_key"] == second["idempotency_key"] == key
        assert second["amount"] == 11_000
        # Stripe saves a 5xx for the key and replays it (24 hours): still in progress.
        # A connection error or a 429 saved nothing, so the retry places it.
        expected = CardHold.Status.SCHEDULED if error is api_error else CardHold.Status.AUTHORIZED
        assert reload(hold).status == expected

    def test_a_conflict_on_the_key_is_in_progress(self, holder, fake_stripe, deferral) -> None:
        from ..fakes import concurrent_request

        hold = due(holder)
        fake_stripe.fail_next("PaymentIntent.create", concurrent_request())

        assert place_scheduled(hold.pk).status == PlacementStatus.IN_PROGRESS
        assert reload(hold).status == CardHold.Status.SCHEDULED

    def test_an_authorization_made_behind_a_lost_answer_is_replayed_not_duplicated(
        self, holder, fake_stripe, deferral
    ) -> None:
        hold = due(holder)
        real = holds._create_off_session
        lost = []

        def lose_the_answer(claimed) -> tuple:
            if not lost:
                lost.append(real(claimed))
                return None, connection_error()
            return real(claimed)

        with patch.object(holds, "_create_off_session", side_effect=lose_the_answer):
            assert place_scheduled(hold.pk).status == PlacementStatus.IN_PROGRESS
            assert place_scheduled(hold.pk).status == PlacementStatus.PLACED

        assert len(fake_stripe.intents) == 1
        (payment_intent_id,) = fake_stripe.intents
        assert reload(hold).stripe_payment_intent_id == payment_intent_id
        assert fake_stripe.calls_to("PaymentIntent.retrieve")  # the replay was re-read

    def test_a_replay_that_cant_be_re_read_is_in_progress(
        self, holder, fake_stripe, deferral
    ) -> None:
        hold = due(holder)
        fake_stripe.fail_next("PaymentIntent.retrieve", connection_error())

        with patch.object(holds, "is_idempotent_replay", return_value=True):
            assert place_scheduled(hold.pk).status == PlacementStatus.IN_PROGRESS

        assert reload(hold).placement_key

    def test_a_settled_authorization_on_a_cancelled_target_is_released(
        self, holder, fake_stripe, deferral, django_capture_on_commit_callbacks
    ) -> None:
        hold = due(holder, placement_key="k-out", placement_amount_cents=11_000)
        HoldableOrder.objects.filter(pk=hold.target.pk).update(status="cancelled")

        with django_capture_on_commit_callbacks(execute=True):
            assert place_scheduled(hold.pk).status == PlacementStatus.REFUSED

        hold = reload(hold)
        assert hold.status == CardHold.Status.RELEASED
        assert hold.release_reason == "cancelled"
        assert fake_stripe.status_of(hold.stripe_payment_intent_id) == "canceled"
        assert hold.release_confirmed_at is not None

    def test_a_settled_authorization_on_a_target_not_holdable_now_goes_back_to_scheduled(
        self, holder, fake_stripe, deferral, django_capture_on_commit_callbacks
    ) -> None:
        """#3: released ``not_holdable`` with its PaymentIntent until Stripe confirms the
        cancel, then back to ``scheduled``, the authorization in the history."""
        hold = due(holder, placement_key="k-out", placement_amount_cents=11_000)

        with (
            patch.object(
                HoldableOrderHoldTarget, "filter_holdable", lambda self, queryset: queryset.none()
            ),
            django_capture_on_commit_callbacks(execute=True),
        ):
            assert place_scheduled(hold.pk).status == PlacementStatus.REFUSED

        hold = reload(hold)
        (payment_intent_id,) = fake_stripe.intents
        assert fake_stripe.status_of(payment_intent_id) == "canceled"
        assert hold.status == CardHold.Status.RELEASED and hold.placement_key == ""
        assert hold.release_reason == CardHold.ReleaseReason.NOT_HOLDABLE
        assert hold.stripe_payment_intent_id == payment_intent_id
        assert hold.release_confirmed_at is not None

        with patch.object(
            HoldableOrderHoldTarget, "filter_holdable", lambda self, queryset: queryset.none()
        ):
            result = reschedule_hold(hold.pk)

        assert result.status == PlacementStatus.REFUSED  # due, but still not holdable
        hold = reload(hold)
        assert hold.status == CardHold.Status.SCHEDULED
        assert hold.stripe_payment_intent_id is None and hold.expires_at is None
        assert hold.previous_payment_intent_ids == [payment_intent_id]

    def test_an_unconfirmed_not_holdable_release_is_never_charged_and_is_re_driven(
        self, holder, fake_stripe, deferral
    ) -> None:
        """#3: the release task was lost. capture() answers in_progress while the
        authorization may be live, and the sweep re-drives its cancel."""
        hold = due(holder, placement_key="k-out", placement_amount_cents=11_000)
        with (
            patch.object(
                HoldableOrderHoldTarget, "filter_holdable", lambda self, queryset: queryset.none()
            ),
            patch.object(holds, "release_on_commit"),
        ):
            assert place_scheduled(hold.pk).status == PlacementStatus.REFUSED
        hold = reload(hold)
        (payment_intent_id,) = fake_stripe.intents
        assert hold.release_reason == CardHold.ReleaseReason.NOT_HOLDABLE
        assert hold.release_confirmed_at is None and hold.expires_at is not None
        charge = Mock()

        assert capture(hold.pk, 11_000, charge=charge).status == CaptureStatus.IN_PROGRESS
        assert capture(hold.pk, 0, charge=charge).status == CaptureStatus.IN_PROGRESS
        charge.assert_not_called()
        assert fake_stripe.status_of(payment_intent_id) == "requires_capture"

        CardHold.objects.filter(pk=hold.pk).update(
            modified=timezone.now() - datetime.timedelta(hours=1)
        )
        with patch.object(tasks.release_card_hold, "delay") as queued:
            sweep_card_holds()
        queued.assert_any_call(hold.pk, claimed=True, payment_intent_id=payment_intent_id)

    def test_a_settled_decline_on_a_cancelled_target_tells_nobody(
        self,
        holder,
        fake_stripe,
        deferral,
        failed_signal,
        mailoutbox,
        staff_member,
        django_capture_on_commit_callbacks,
    ) -> None:
        hold = due(holder, placement_key="k-out", placement_amount_cents=11_000)
        HoldableOrder.objects.filter(pk=hold.target.pk).update(status="cancelled")
        fake_stripe.next_outcome = ["card_declined"]

        with django_capture_on_commit_callbacks(execute=True):
            place_scheduled(hold.pk)

        hold = reload(hold)
        assert hold.status == CardHold.Status.RELEASED and hold.failed_at is None
        assert failed_signal.sent == [] and mailoutbox == []

    def test_the_adapter_decides_how_staff_hear(
        self, holder, fake_stripe, deferral, mailoutbox, django_capture_on_commit_callbacks
    ) -> None:
        hold = due(holder)
        fake_stripe.next_outcome = ["card_declined"]
        told = []

        with (
            patch.object(
                HoldableOrderHoldTarget,
                "notify_hold_failed",
                lambda self, target, failed: told.append((target, failed)),
            ),
            django_capture_on_commit_callbacks(execute=True),
        ):
            place_scheduled(hold.pk)

        assert told == [(hold.target, reload(hold))]
        assert mailoutbox == []

    def test_staff_recipients_choose_who_is_emailed_in_their_language(
        self, holder, fake_stripe, deferral, mailoutbox, django_capture_on_commit_callbacks
    ) -> None:
        hold = due(holder)
        fake_stripe.next_outcome = ["card_declined"]
        spanish = UserFactory(email="es@example.com", preferred_language="es")
        english = UserFactory(email="en@example.com", preferred_language="en")
        no_email = UserFactory(email="")

        with (
            patch.object(
                HoldableOrderHoldTarget,
                "staff_recipients",
                lambda self, target: [spanish, english, no_email],
            ),
            django_capture_on_commit_callbacks(execute=True),
        ):
            place_scheduled(hold.pk)

        by_recipient = {tuple(mail.to): mail for mail in mailoutbox}
        assert set(by_recipient) == {("es@example.com",), ("en@example.com",)}
        assert by_recipient[("en@example.com",)].subject.startswith("Card hold failed")
        assert not by_recipient[("es@example.com",)].subject.startswith("Card hold failed")

    def test_no_recipients_no_email(
        self, holder, fake_stripe, deferral, mailoutbox, django_capture_on_commit_callbacks
    ) -> None:
        hold = due(holder)
        fake_stripe.next_outcome = ["card_declined"]

        with django_capture_on_commit_callbacks(execute=True):
            place_scheduled(hold.pk)

        assert mailoutbox == []


# --- 4. Staff decisions ---------------------------------------------------------------


def failed(holder, **fields) -> Any:
    return due(
        holder,
        status=CardHold.Status.FAILED,
        failed_at=timezone.now(),
        failure_code="card_declined",
        **fields,
    )


class TestStaffDecisions:
    def test_keeping_lets_the_target_close_by_a_fresh_charge(
        self, holder, staff_member, fake_stripe
    ) -> None:
        hold = failed(holder)
        charges = []

        def charge(idempotency_key) -> str:
            charges.append(idempotency_key)
            return "ch_1"

        assert capture(hold.pk, 10_000, charge=charge).status == CaptureStatus.NOT_CAPTURED
        assert charges == []

        assert keep_failed_hold(hold.pk, staff_member) is True

        hold = reload(hold)
        assert hold.kept_at is not None and hold.kept_by == staff_member
        assert hold.status == CardHold.Status.FAILED
        result = capture(hold.pk, 10_000, charge=charge)
        assert result.status == CaptureStatus.CHARGED and result.charge == "ch_1"
        assert capture(hold.pk, 10_000, charge=charge).status == CaptureStatus.CHARGED
        assert charges == [f"testproject-charge-{hold.pk}-0"]
        assert fake_stripe.calls == []

    def test_cancelling_a_hold_on_an_unregistered_target_is_refused(
        self, holder, staff_member, settings, caplog
    ) -> None:
        """#10: nothing could cancel the target, so the hold isn't released either."""
        hold = failed(holder)
        settings.BASEAPP_PAYMENTS_CARD_HOLD_TARGETS = {}

        with caplog.at_level("ERROR", logger="baseapp_payments.holds"):
            assert cancel_failed_hold(hold.pk, staff_member) is False

        assert "can't be cancelled" in caplog.text
        hold = reload(hold)
        assert hold.status == CardHold.Status.FAILED
        assert hold.target.status == HoldableOrder.Status.OPEN

    def test_kept_is_final(self, holder, staff_member) -> None:
        hold = failed(holder)
        keep_failed_hold(hold.pk, staff_member)

        assert keep_failed_hold(hold.pk, staff_member) is False
        assert cancel_failed_hold(hold.pk, staff_member) is False
        assert reload(hold).target.status == HoldableOrder.Status.OPEN

    def test_cancelling_cancels_the_target_and_charges_nothing(
        self, holder, staff_member, fake_stripe, django_capture_on_commit_callbacks
    ) -> None:
        hold = failed(holder)
        cancelled_by = []
        real_cancel = HoldableOrderHoldTarget.cancel

        def cancel(self, target, actor) -> None:
            cancelled_by.append(actor)
            real_cancel(self, target, actor)

        with (
            patch.object(HoldableOrderHoldTarget, "cancel", cancel),
            django_capture_on_commit_callbacks(execute=True),
        ):
            assert cancel_failed_hold(hold.pk, staff_member) is True

        hold = reload(hold)
        assert cancelled_by == [staff_member]
        assert hold.target.status == HoldableOrder.Status.CANCELLED
        assert hold.status == CardHold.Status.RELEASED
        assert hold.release_reason == "cancelled" and hold.release_confirmed_at
        assert hold.failed_at is not None
        assert fake_stripe.calls == []
        assert not card_in_use(holder, "pm_visa")
        assert cancel_failed_hold(hold.pk, staff_member) is False
        assert not holds._rearmable(hold)

    def test_a_cancel_hook_that_raises_changes_nothing(self, holder, staff_member) -> None:
        hold = failed(holder)

        with (
            patch.object(HoldableOrderHoldTarget, "cancel", side_effect=RuntimeError),
            pytest.raises(RuntimeError),
        ):
            cancel_failed_hold(hold.pk, staff_member)

        assert reload(hold).status == CardHold.Status.FAILED

    def test_a_failed_hold_whose_target_is_gone_is_just_closed(self, holder, staff_member) -> None:
        hold = failed(holder)
        hold.target.delete()

        assert cancel_failed_hold(hold.pk, staff_member) is True
        assert reload(hold).status == CardHold.Status.RELEASED

    @pytest.mark.parametrize("status", ["scheduled", "authorized", "released", "captured"])
    def test_only_a_failed_hold_is_decided(self, holder, staff_member, status) -> None:
        hold = due(holder, status=status)

        assert keep_failed_hold(hold.pk, staff_member) is False
        assert cancel_failed_hold(hold.pk, staff_member) is False
        assert reload(hold).status == status

    def test_an_anonymous_keep_records_no_one(self, holder) -> None:
        hold = failed(holder)

        assert keep_failed_hold(hold.pk, None) is True
        assert reload(hold).kept_by is None


# --- 5. A change of date ----------------------------------------------------------------


def placed(holder, target_date: datetime.date, fake_stripe) -> Any:
    """An authorized hold, live in the fake Stripe."""
    order = HoldableOrderFactory(user=holder, target_date=target_date)
    hold = CardHoldFactory(target=order)
    fake_stripe.intents[hold.stripe_payment_intent_id] = {
        "id": hold.stripe_payment_intent_id,
        "object": "payment_intent",
        "status": "requires_capture",
        "amount": hold.amount_cents,
        "payment_method": "pm_visa",
        "capture_before": None,
    }
    return hold


def move(hold, target_date: datetime.date | None) -> HoldableOrder:
    order = hold.target
    order.target_date = target_date
    order.save()
    return order


class TestReschedule:
    def test_a_placed_hold_moved_out_of_the_window_goes_back_to_scheduled(
        self, holder, fake_stripe, deferral, django_capture_on_commit_callbacks
    ) -> None:
        hold = placed(holder, days(3), fake_stripe)
        old = hold.stripe_payment_intent_id

        with django_capture_on_commit_callbacks(execute=True):
            result = reschedule(move(hold, days(20)))

        assert result.status == PlacementStatus.SCHEDULED and result.hold_on == days(16)
        hold = reload(hold)
        assert hold.status == CardHold.Status.SCHEDULED
        assert hold.stripe_payment_intent_id is None and hold.expires_at is None
        assert hold.previous_payment_intent_ids == [old]
        assert hold.release_reason == "" and hold.release_confirmed_at is None
        assert fake_stripe.status_of(old) == "canceled"
        assert CardHold.objects.count() == 1
        # Placed again later with a new key, never replaying the old authorization.
        assert scheduled_idempotency_key(hold).endswith("-1")

    def test_a_placed_hold_still_inside_the_window_is_left_alone(
        self, holder, fake_stripe, deferral
    ) -> None:
        hold = placed(holder, days(3), fake_stripe)

        assert reschedule(move(hold, days(4))) is None
        assert reload(hold).status == CardHold.Status.AUTHORIZED
        assert fake_stripe.calls == []

    def test_a_date_moved_past_the_authorizations_expiry_is_placed_again(
        self, holder, fake_stripe, deferral, django_capture_on_commit_callbacks
    ) -> None:
        """#9: still inside the window, but the authorization lapses before the new date:
        released, then placed again off-session at once (its day has come)."""
        hold = placed(holder, days(2), fake_stripe)
        old = hold.stripe_payment_intent_id
        CardHold.objects.filter(pk=hold.pk).update(
            expires_at=timezone.now() + datetime.timedelta(days=2, hours=1)
        )

        with django_capture_on_commit_callbacks(execute=True):
            result = reschedule(move(hold, days(4)))

        assert result.status == PlacementStatus.PLACED
        hold = reload(hold)
        assert hold.status == CardHold.Status.AUTHORIZED
        assert hold.stripe_payment_intent_id != old
        assert hold.previous_payment_intent_ids == [old]
        assert fake_stripe.status_of(old) == "canceled"
        (params,) = creates(fake_stripe)
        assert params["off_session"] is True

    def test_a_date_moved_later_within_the_authorizations_life_is_left_alone(
        self, holder, fake_stripe, deferral
    ) -> None:
        hold = placed(holder, days(2), fake_stripe)
        CardHold.objects.filter(pk=hold.pk).update(
            expires_at=timezone.now() + datetime.timedelta(days=4, hours=18)
        )

        assert reschedule(move(hold, days(4))) is None
        assert reload(hold).status == CardHold.Status.AUTHORIZED
        assert fake_stripe.calls == []

    def test_a_scheduled_hold_gets_its_new_day(self, holder, fake_stripe, deferral) -> None:
        hold = scheduled(holder)

        result = reschedule(move(hold, days(40)))

        assert result.status == PlacementStatus.SCHEDULED
        assert reload(hold).hold_on == days(36)
        assert fake_stripe.calls == []

    @pytest.mark.parametrize("target_date", [2, None])
    def test_a_scheduled_hold_moved_into_the_window_is_placed_now(
        self, holder, fake_stripe, deferral, target_date
    ) -> None:
        hold = scheduled(holder)

        result = reschedule(move(hold, days(target_date) if target_date else None))

        assert result.status == PlacementStatus.PLACED
        (params,) = creates(fake_stripe)
        assert params["off_session"] is True
        assert reload(hold).status == CardHold.Status.AUTHORIZED

    def test_one_that_then_fails_fails_like_the_sweep(
        self, holder, fake_stripe, deferral, failed_signal, django_capture_on_commit_callbacks
    ) -> None:
        hold = scheduled(holder)
        fake_stripe.next_outcome = ["authentication_required"]

        with django_capture_on_commit_callbacks(execute=True):
            result = reschedule(move(hold, days(1)))

        assert result.status == PlacementStatus.DECLINED
        assert reload(hold).status == CardHold.Status.FAILED
        assert len(failed_signal.sent) == 1

    @pytest.mark.parametrize("kept", [False, True])
    def test_failed_and_kept_holds_are_excluded(self, holder, fake_stripe, deferral, kept) -> None:
        hold = failed(holder, kept_at=timezone.now() if kept else None)

        assert reschedule(move(hold, days(1))) is None
        assert reload(hold).status == CardHold.Status.FAILED
        assert fake_stripe.calls == []

    def test_without_deferral_nothing_happens(self, holder, fake_stripe) -> None:
        hold = placed(holder, days(3), fake_stripe)

        assert reschedule(move(hold, days(30))) is None
        reschedule_on_commit(hold.target)
        assert reload(hold).status == CardHold.Status.AUTHORIZED

    def test_an_unsaved_or_unheld_target_has_nothing_to_reschedule(self, holder, deferral) -> None:
        assert reschedule(HoldableOrder(user=holder)) is None
        assert reschedule(HoldableOrderFactory(user=holder)) is None
        assert reschedule_hold(CardHoldFactory(customer=holder).pk) is None

    def test_a_scheduled_hold_being_placed_is_in_progress(
        self, holder, fake_stripe, deferral
    ) -> None:
        hold = scheduled(holder, placement_key="k", placement_amount_cents=1)

        assert reschedule(move(hold, days(40))).status == PlacementStatus.IN_PROGRESS
        assert reload(hold).hold_on == days(26)

    def test_a_hold_being_captured_is_in_progress(self, holder, fake_stripe, deferral) -> None:
        hold = placed(holder, days(3), fake_stripe)
        CardHold.objects.filter(pk=hold.pk).update(capture_claimed_at=timezone.now())

        assert reschedule(move(hold, days(30))).status == PlacementStatus.IN_PROGRESS
        assert reload(hold).status == CardHold.Status.AUTHORIZED

    def test_a_hold_stripe_reports_captured_is_recorded_captured(
        self, holder, fake_stripe, deferral
    ) -> None:
        hold = placed(holder, days(3), fake_stripe)
        fake_stripe.set_status(hold.stripe_payment_intent_id, "succeeded")

        assert reschedule(move(hold, days(30))) is None
        assert reload(hold).status == CardHold.Status.CAPTURED

    def test_a_refused_cancel_is_finished_by_the_sweep(
        self, holder, fake_stripe, deferral, django_capture_on_commit_callbacks
    ) -> None:
        hold = placed(holder, days(3), fake_stripe)
        fake_stripe.fail_next(
            "PaymentIntent.cancel",
            unexpected_state(hold.stripe_payment_intent_id, "processing", "cancel"),
        )

        assert reschedule(move(hold, days(30))).status == PlacementStatus.IN_PROGRESS
        hold = reload(hold)
        assert hold.status == CardHold.Status.RELEASED
        assert hold.release_reason == "rescheduled" and hold.release_confirmed_at is None
        # Never re-armed on the customer's next try while it is being moved.
        assert not holds._rearmable(hold)
        CardHold.objects.filter(pk=hold.pk).update(
            modified=timezone.now() - datetime.timedelta(hours=1)
        )

        with django_capture_on_commit_callbacks(execute=True):
            sweep_card_holds()  # re-drives the cancel...
            sweep_card_holds()  # ...then puts the row back to scheduled

        hold = reload(hold)
        assert hold.status == CardHold.Status.SCHEDULED and hold.hold_on == days(26)

    def test_a_target_cancelled_before_it_is_scheduled_again_stays_released(
        self, holder, fake_stripe, deferral
    ) -> None:
        hold = placed(holder, days(3), fake_stripe)
        CardHold.objects.filter(pk=hold.pk).update(
            status="released", release_reason="rescheduled", release_confirmed_at=timezone.now()
        )
        HoldableOrder.objects.filter(pk=hold.target.pk).update(status="cancelled")

        assert reschedule_hold(hold.pk) is None

        hold = reload(hold)
        assert hold.status == CardHold.Status.RELEASED and hold.release_reason == "cancelled"

    def test_a_transient_error_propagates_and_the_task_retries(
        self, holder, fake_stripe, deferral, eager_retries, django_capture_on_commit_callbacks
    ) -> None:
        hold = placed(holder, days(3), fake_stripe)
        fake_stripe.fail_next("PaymentIntent.cancel", connection_error())
        move(hold, days(30))

        with django_capture_on_commit_callbacks(execute=True):
            reschedule_on_commit(hold.target)

        assert reload(hold).status == CardHold.Status.SCHEDULED
        assert len(fake_stripe.calls_to("PaymentIntent.cancel")) == 2

    def test_the_task_gives_up_after_its_retries(
        self, holder, fake_stripe, deferral, eager_retries, caplog
    ) -> None:
        hold = scheduled(holder, placement_key="k", placement_amount_cents=1)

        with patch.object(tasks, "backoff_countdown", return_value=0):
            reschedule_card_hold.delay(hold.pk)

        assert "Gave up rescheduling" in caplog.text

    def test_the_task_is_a_no_op_without_stripe(self, holder, deferral, settings) -> None:
        settings.STRIPE_SECRET_KEY = ""
        hold = scheduled(holder)

        reschedule_card_hold.delay(hold.pk)
        tasks.place_card_hold(hold.pk)

        assert reload(hold).status == CardHold.Status.SCHEDULED


# --- 6. Cancelling before placement ----------------------------------------------------


class TestReleasingBeforePlacement:
    def test_cancelling_the_target_releases_it_without_stripe(
        self, holder, fake_stripe, deferral, django_capture_on_commit_callbacks
    ) -> None:
        hold = scheduled(holder)
        order = hold.target
        assert card_in_use(holder, "pm_visa")
        order.status = HoldableOrder.Status.CANCELLED
        order.save()

        with django_capture_on_commit_callbacks(execute=True):
            release_target_holds_on_commit(order)

        hold = reload(hold)
        assert hold.status == CardHold.Status.RELEASED
        assert hold.release_reason == "cancelled" and hold.release_confirmed_at
        assert fake_stripe.calls == []
        assert not card_in_use(holder, "pm_visa")

    def test_the_sweep_releases_scheduled_holds_on_cancelled_targets(
        self, holder, fake_stripe
    ) -> None:
        hold = scheduled(holder)
        HoldableOrder.objects.filter(pk=hold.target.pk).update(status="cancelled")

        sweep_card_holds()

        assert reload(hold).status == CardHold.Status.RELEASED
        assert fake_stripe.calls == []

    def test_deleting_the_target_releases_it(
        self, holder, fake_stripe, django_capture_on_commit_callbacks
    ) -> None:
        hold = scheduled(holder)

        with django_capture_on_commit_callbacks(execute=True):
            hold.target.delete()

        assert reload(hold).status == CardHold.Status.RELEASED
        assert fake_stripe.calls == []

    def test_a_hold_being_placed_is_left_to_its_placement(self, holder, fake_stripe) -> None:
        hold = scheduled(holder, placement_key="k", placement_amount_cents=1)
        HoldableOrder.objects.filter(pk=hold.target.pk).update(status="cancelled")

        assert release(hold.pk) is False
        assert release_for_charge(hold.pk) is False
        assert reload(hold).status == CardHold.Status.SCHEDULED

    def test_release_for_charge_needs_no_stripe(self, holder, fake_stripe) -> None:
        hold = scheduled(holder)

        assert release_for_charge(hold.pk) is True

        hold = reload(hold)
        assert hold.status == CardHold.Status.RELEASED and hold.release_reason == "for_charge"
        assert fake_stripe.calls == []

    def test_capturing_a_scheduled_hold_releases_it_and_charges_once(
        self, holder, fake_stripe
    ) -> None:
        hold = scheduled(holder)
        charges = []

        result = capture(hold.pk, 9_000, charge=lambda idempotency_key: charges.append(1) or "c")

        assert result.status == CaptureStatus.CHARGED and charges == [1]
        hold = reload(hold)
        assert hold.status == CardHold.Status.RELEASED and hold.charged_at is not None
        assert fake_stripe.calls == []

    def test_capturing_one_being_placed_is_in_progress(self, holder, fake_stripe) -> None:
        hold = scheduled(holder, placement_key="k", placement_amount_cents=1)

        result = capture(hold.pk, 9_000, charge=lambda idempotency_key: pytest.fail("charged"))

        assert result.status == CaptureStatus.IN_PROGRESS

    def test_an_active_targets_scheduled_hold_isnt_released(self, holder, fake_stripe) -> None:
        hold = scheduled(holder)

        assert release(hold.pk) is False
        assert reload(hold).status == CardHold.Status.SCHEDULED

    def test_a_target_already_holding_a_scheduled_hold_refuses_another(
        self, holder, fake_stripe, deferral
    ) -> None:
        hold = scheduled(holder)

        assert place(holder, hold.target).status == PlacementStatus.REFUSED
        assert fake_stripe.calls == []


class TestEdges:
    def test_an_unregistered_target_is_never_placed_or_rescheduled(
        self, holder, fake_stripe, deferral
    ) -> None:
        hold = due(holder)

        with patch.object(holds, "target_for_content_type_id", return_value=None):
            assert place_scheduled(hold.pk) is None
            assert reschedule_hold(hold.pk) is None

        assert fake_stripe.calls == []

    def test_a_setup_intent_still_processing_is_in_progress(
        self, holder, fake_stripe, deferral
    ) -> None:
        fake_stripe.next_setup_outcome = ["processing"]

        result = place(holder, HoldableOrder(user=holder, target_date=days(30)))

        assert result.status == PlacementStatus.IN_PROGRESS
        assert CardHold.objects.get().status == CardHold.Status.PENDING

    def test_a_replayed_setup_intent_that_cant_be_re_read_is_in_progress(
        self, holder, fake_stripe, deferral
    ) -> None:
        fake_stripe.fail_next("SetupIntent.retrieve", connection_error())

        with patch.object(holds, "is_idempotent_replay", return_value=True):
            result = place(holder, HoldableOrder(user=holder, target_date=days(30)))

        assert result.status == PlacementStatus.IN_PROGRESS

    def test_abandoning_no_setup_intent_does_nothing(self) -> None:
        assert holds.abandon_setup(None) is None
        assert holds.abandon_setup("seti_unknown") is None

    def test_the_second_pass_answers_a_scheduled_attempt_first(
        self, holder, fake_stripe, deferral
    ) -> None:
        attempt_id = uuid.uuid4()
        place(holder, HoldableOrder(user=holder, target_date=days(30)), attempt_id)

        result = complete_setup_on_session(
            "seti_whatever",
            user=holder,
            attempt_id=attempt_id,
            stripe_customer_id=STRIPE_CUSTOMER_ID,
        )

        assert result.status == PlacementStatus.SCHEDULED

    def test_a_claim_taken_over_meanwhile_leaves_the_answer_to_the_taker(
        self, holder, fake_stripe, deferral
    ) -> None:
        hold = due(holder)
        real = holds._create_off_session

        def taken_over(claimed) -> tuple:
            answer = real(claimed)
            CardHold.objects.filter(pk=claimed.pk).update(placement_key="someone-else")
            return answer

        with patch.object(holds, "_create_off_session", side_effect=taken_over):
            assert place_scheduled(hold.pk).status == PlacementStatus.IN_PROGRESS

        assert reload(hold).status == CardHold.Status.SCHEDULED

    def test_a_reschedule_to_the_same_day_writes_nothing(
        self, holder, fake_stripe, deferral
    ) -> None:
        hold = scheduled(holder)
        modified = hold.modified

        assert reschedule(hold.target).status == PlacementStatus.SCHEDULED
        assert reload(hold).modified == modified

    def test_a_reschedule_of_a_deleted_target_does_nothing(
        self, holder, fake_stripe, deferral
    ) -> None:
        hold = scheduled(holder)
        with patch.object(HoldableOrderHoldTarget, "lock", return_value=None):
            assert reschedule_hold(hold.pk) is None

    def test_a_hold_moved_back_whose_day_came_meanwhile_is_placed_at_once(
        self, holder, fake_stripe, deferral
    ) -> None:
        hold = placed(holder, days(2), fake_stripe)
        CardHold.objects.filter(pk=hold.pk).update(
            status="released", release_reason="rescheduled", release_confirmed_at=timezone.now()
        )

        result = reschedule_hold(hold.pk)

        assert result.status == PlacementStatus.PLACED
        hold = reload(hold)
        assert hold.status == CardHold.Status.AUTHORIZED
        assert len(hold.previous_payment_intent_ids) == 1

    def test_a_decided_hold_that_changed_meanwhile_isnt_decided(self, holder, staff_member) -> None:
        hold = failed(holder)
        real_lock = HoldableOrderHoldTarget.lock

        def lock_then_keep(self, target_pk) -> Any:
            CardHold.objects.filter(pk=hold.pk).update(kept_at=timezone.now())
            return real_lock(self, target_pk)

        with patch.object(HoldableOrderHoldTarget, "lock", lock_then_keep):
            assert keep_failed_hold(hold.pk, staff_member) is False

    def test_a_claim_on_a_hold_placed_meanwhile_does_nothing(
        self, holder, fake_stripe, deferral
    ) -> None:
        hold = due(holder)
        real_lock = HoldableOrderHoldTarget.lock

        def lock_then_place(self, target_pk) -> Any:
            CardHold.objects.filter(pk=hold.pk).update(status="authorized")
            return real_lock(self, target_pk)

        with patch.object(HoldableOrderHoldTarget, "lock", lock_then_place):
            assert place_scheduled(hold.pk) is None

        assert fake_stripe.calls == []

    def test_a_hold_relinked_meanwhile_is_left_alone(self, holder, fake_stripe, deferral) -> None:
        hold = due(holder)
        other = HoldableOrderFactory(user=holder)
        real_lock = HoldableOrderHoldTarget.lock

        def lock_then_relink(self, target_pk) -> Any:
            from baseapp_core.models import DocumentId

            CardHold.objects.filter(pk=hold.pk).update(
                target_document=DocumentId.get_or_create_for_object(other)
            )
            return real_lock(self, target_pk)

        with patch.object(HoldableOrderHoldTarget, "lock", lock_then_relink):
            assert place_scheduled(hold.pk) is None
