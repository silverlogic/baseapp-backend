"""Staff retrying a failed deferred hold (``retry_failed_hold``, ``cardHoldRetry``): a new
off-session attempt on the same card, with a new key, up to ``CARD_HOLDS_MAX_RETRIES``.
Stripe is the in-memory ``FakeStripe``."""

import datetime
from collections.abc import Generator
from typing import Any
from unittest.mock import patch

import pytest
import swapper
from constance.test import override_config
from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory
from django.utils import timezone

from baseapp_core.graphql import get_obj_relay_id
from baseapp_payments import holds
from baseapp_payments.holds import (
    CaptureStatus,
    PlacementStatus,
    RetryRefusal,
    cancel_failed_hold,
    capture,
    keep_failed_hold,
    place_scheduled,
    reconcile_payment_intent,
    release_target_holds_on_commit,
    reschedule_hold,
    retries_left,
    retry_failed_hold,
)
from baseapp_payments.signals import (
    card_hold_authorized,
    card_hold_failed,
    card_hold_retried,
)
from baseapp_payments.tasks import sweep_card_holds
from testproject.testapp.card_holds import HoldableOrderHoldTarget
from testproject.testapp.models import HoldableOrder

from ..card_hold_factories import CardHoldFactory, HoldableOrderFactory
from ..factories import UserFactory
from ..fakes import api_error, connection_error
from ..helpers import grant_card_hold_perm

CardHold = swapper.load_model("baseapp_payments", "CardHold")

pytestmark = pytest.mark.django_db


def days(count: int) -> datetime.date:
    return timezone.localdate() + datetime.timedelta(days=count)


def failed(holder, *, target_date: int = 4, **fields: Any) -> Any:
    """A deferred hold whose off-session placement was declined (``pi_failed``)."""
    order = HoldableOrderFactory(user=holder, target_date=days(target_date))
    fields.setdefault("stripe_payment_intent_id", "pi_failed")
    fields.setdefault("status", CardHold.Status.FAILED)
    fields.setdefault("failed_at", timezone.now())
    fields.setdefault("failure_code", "card_declined")
    return CardHoldFactory(
        target=order,
        expires_at=None,
        hold_on=timezone.localdate(),
        **fields,
    )


def failed_by_the_sweep(holder, fake_stripe) -> Any:
    """A due scheduled hold the sweep's off-session placement got declined."""
    hold = failed(
        holder, status=CardHold.Status.SCHEDULED, failed_at=None, stripe_payment_intent_id=None
    )
    fake_stripe.next_outcome = ["card_declined"]
    with override_config(CARD_HOLDS_DEFERRAL_ENABLED=True):
        assert place_scheduled(hold.pk).status == PlacementStatus.DECLINED
    return reload(hold)


def reload(hold) -> Any:
    hold.refresh_from_db()
    return hold


def creates(fake_stripe) -> list[dict]:
    return [params for _args, params in fake_stripe.calls_to("PaymentIntent.create")]


class Listener:
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
def signals() -> Generator[dict[str, Listener], None, None]:
    listeners = {
        "retried": Listener(card_hold_retried),
        "authorized": Listener(card_hold_authorized),
        "failed": Listener(card_hold_failed),
    }
    yield listeners
    for listener in listeners.values():
        listener.close()


@pytest.fixture
def staff_member(db) -> Any:
    return grant_card_hold_perm(UserFactory(is_staff=True, email="ops@example.com"))


# --- The service --------------------------------------------------------------------


class TestARetryThatSucceeds:
    def test_it_is_placed_off_session_on_the_same_card_and_authorized(
        self,
        holder,
        fake_stripe,
        staff_member,
        signals,
        mailoutbox,
        django_capture_on_commit_callbacks,
    ) -> None:
        hold = failed(holder)

        with django_capture_on_commit_callbacks(execute=True):
            result = retry_failed_hold(hold.pk, staff_member)

        assert result.status == PlacementStatus.PLACED and result.refusal is None
        (params,) = creates(fake_stripe)
        assert params["off_session"] is True and params["confirm"] is True
        assert params["payment_method"] == "pm_visa"
        assert params["capture_method"] == "manual"
        assert params["amount"] == 11_000
        hold = reload(hold)
        assert hold.status == CardHold.Status.AUTHORIZED
        assert hold.failed_at is None and hold.failure_code == ""
        assert hold.stripe_payment_intent_id == fake_stripe.live_authorizations()[0]
        assert hold.previous_payment_intent_ids == ["pi_failed"]
        assert hold.retry_count == 1 and hold.last_retried_by == staff_member
        assert hold.last_retried_at is not None
        assert hold.placement_key == "" and hold.placement_claimed_at is None
        assert [sent["hold"].pk for sent in signals["retried"].sent] == [hold.pk]
        assert signals["retried"].sent[0]["actor"] == staff_member
        assert signals["retried"].sent[0]["target"] == hold.target
        assert len(signals["authorized"].sent) == 1
        assert signals["failed"].sent == [] and mailoutbox == []

    def test_a_new_key_is_used_never_the_failed_one(
        self, holder, fake_stripe, staff_member
    ) -> None:
        hold = failed_by_the_sweep(holder, fake_stripe)
        failed_key = creates(fake_stripe)[0]["idempotency_key"]
        assert reload(hold).status == CardHold.Status.FAILED

        retry_failed_hold(hold.pk, staff_member)

        place_key = creates(fake_stripe)[1]["idempotency_key"]
        assert place_key != failed_key
        assert reload(hold).placement_generation == 1
        assert reload(hold).status == CardHold.Status.AUTHORIZED

    def test_it_is_priced_now(self, holder, fake_stripe, staff_member) -> None:
        hold = failed(holder)
        HoldableOrder.objects.filter(pk=hold.target.pk).update(amount_cents=20_000)

        retry_failed_hold(hold.pk, staff_member)

        assert creates(fake_stripe)[0]["amount"] == 22_000
        hold = reload(hold)
        assert hold.amount_cents == 22_000 and hold.estimated_amount_cents == 20_000

    def test_a_retried_hold_then_captures_like_any_other(
        self, holder, fake_stripe, staff_member
    ) -> None:
        hold = failed(holder)
        retry_failed_hold(hold.pk, staff_member)

        result = capture(hold.pk, 10_000, charge=lambda **kwargs: None)

        assert result.status == CaptureStatus.CAPTURED
        assert reload(hold).payment_status == CardHold.PaymentStatus.PAID

    def test_a_retried_hold_released_by_a_cancel_may_be_re_armed(
        self, holder, fake_stripe, staff_member, django_capture_on_commit_callbacks
    ) -> None:
        hold = failed(holder)
        retry_failed_hold(hold.pk, staff_member)
        HoldableOrder.objects.filter(pk=hold.target.pk).update(status="cancelled")

        with django_capture_on_commit_callbacks(execute=True):
            release_target_holds_on_commit(hold.target)

        hold = reload(hold)
        assert hold.status == CardHold.Status.RELEASED and hold.release_confirmed_at
        assert holds._rearmable(hold)

    def test_an_anonymous_actor_records_no_one(self, holder, fake_stripe) -> None:
        hold = failed(holder)

        retry_failed_hold(hold.pk, AnonymousUser())

        assert reload(hold).last_retried_by is None


class TestARetryThatFailsAgain:
    def test_it_fails_again_and_staff_are_emailed(
        self,
        holder,
        fake_stripe,
        staff_member,
        signals,
        mailoutbox,
        django_capture_on_commit_callbacks,
    ) -> None:
        hold = failed(holder)
        fake_stripe.next_outcome = ["insufficient_funds"]

        with django_capture_on_commit_callbacks(execute=True):
            result = retry_failed_hold(hold.pk, staff_member)

        assert result.status == PlacementStatus.DECLINED and result.refusal is None
        hold = reload(hold)
        assert hold.status == CardHold.Status.FAILED
        assert hold.failure_code == "insufficient_funds" and hold.failed_at is not None
        assert hold.retry_count == 1
        assert retries_left(hold) == 2
        (new_payment_intent,) = fake_stripe.intents
        assert hold.stripe_payment_intent_id == new_payment_intent
        assert hold.previous_payment_intent_ids == ["pi_failed"]
        assert len(signals["failed"].sent) == 1
        (mail,) = mailoutbox
        assert mail.to == ["ops@example.com"]
        assert "insufficient_funds" in mail.body

    def test_retries_count_up_to_the_limit_then_are_refused_without_stripe(
        self, holder, fake_stripe, staff_member
    ) -> None:
        hold = failed(holder)
        fake_stripe.next_outcome = ["card_declined"] * 3

        for attempt in range(3):
            assert retry_failed_hold(hold.pk, staff_member).status == PlacementStatus.DECLINED
            assert reload(hold).retry_count == attempt + 1
        keys = {params["idempotency_key"] for params in creates(fake_stripe)}
        assert len(keys) == 3

        result = retry_failed_hold(hold.pk, staff_member)

        assert result.status == PlacementStatus.REFUSED
        assert result.refusal == RetryRefusal.NO_RETRIES_LEFT
        assert len(creates(fake_stripe)) == 3
        hold = reload(hold)
        assert hold.status == CardHold.Status.FAILED and retries_left(hold) == 0
        # Only keep or cancel remain.
        assert keep_failed_hold(hold.pk, staff_member) is True

    def test_the_limit_is_a_constance_key(self, holder, fake_stripe, staff_member) -> None:
        hold = failed(holder)
        fake_stripe.next_outcome = ["card_declined"]

        with override_config(CARD_HOLDS_MAX_RETRIES=1):
            retry_failed_hold(hold.pk, staff_member)
            assert retries_left(reload(hold)) == 0
            result = retry_failed_hold(hold.pk, staff_member)

        assert result.refusal == RetryRefusal.NO_RETRIES_LEFT
        assert len(creates(fake_stripe)) == 1

    @pytest.mark.parametrize("setting", [0, -2])
    def test_zero_keeps_failed_holds_final(
        self, holder, fake_stripe, staff_member, setting
    ) -> None:
        hold = failed(holder)

        with override_config(CARD_HOLDS_MAX_RETRIES=setting):
            result = retry_failed_hold(hold.pk, staff_member)
            assert retries_left(reload(hold)) == 0

        assert result.refusal == RetryRefusal.NO_RETRIES_LEFT
        assert fake_stripe.calls == []
        assert reload(hold).status == CardHold.Status.FAILED


class TestRefusals:
    def test_a_kept_hold_is_refused(self, holder, fake_stripe, staff_member) -> None:
        hold = failed(holder)
        keep_failed_hold(hold.pk, staff_member)

        result = retry_failed_hold(hold.pk, staff_member)

        assert result.refusal == RetryRefusal.NOT_FAILED
        assert retries_left(reload(hold)) == 0
        assert fake_stripe.calls == []

    def test_a_cancelled_hold_is_refused(self, holder, fake_stripe, staff_member) -> None:
        hold = failed(holder)
        cancel_failed_hold(hold.pk, staff_member)

        result = retry_failed_hold(hold.pk, staff_member)

        assert result.refusal == RetryRefusal.NOT_FAILED
        assert retries_left(reload(hold)) is None
        assert reload(hold).status == CardHold.Status.RELEASED
        assert fake_stripe.calls == []

    @pytest.mark.parametrize("status", ["scheduled", "authorized", "released", "captured"])
    def test_a_hold_that_isnt_failed_is_refused(
        self, holder, fake_stripe, staff_member, status
    ) -> None:
        hold = CardHoldFactory(target=HoldableOrderFactory(user=holder), status=status)

        result = retry_failed_hold(hold.pk, staff_member)

        assert result.refusal == RetryRefusal.NOT_FAILED
        assert retries_left(hold) is None
        assert reload(hold).status == status
        assert fake_stripe.calls == []

    def test_an_unknown_id_is_refused(self, fake_stripe, staff_member) -> None:
        result = retry_failed_hold(0, staff_member)

        assert result.refusal == RetryRefusal.NOT_FAILED and result.hold is None

    @pytest.mark.parametrize(
        "change, refusal",
        [
            ({"status": "cancelled"}, RetryRefusal.NOT_HOLDABLE),
            ({"status": "charged"}, RetryRefusal.NOT_HOLDABLE),
            ({"filter_holdable": None}, RetryRefusal.NOT_HOLDABLE),
            ({"target_date": 0}, RetryRefusal.DATE_PASSED),
            ({"target_date": -3}, RetryRefusal.DATE_PASSED),
            ({"target_date": None}, RetryRefusal.DATE_PASSED),
            ({"amount_cents": 0}, RetryRefusal.NOT_HOLDABLE),
        ],
    )
    def test_a_target_no_longer_holdable_is_refused_without_stripe(
        self, holder, fake_stripe, staff_member, change, refusal
    ) -> None:
        hold = failed(holder)
        if "target_date" in change and change["target_date"] is not None:
            change = {"target_date": days(change["target_date"])}
        holdable = HoldableOrderHoldTarget.filter_holdable
        if "filter_holdable" in change:
            change, holdable = {}, lambda self, queryset: queryset.none()
        HoldableOrder.objects.filter(pk=hold.target.pk).update(**change)

        with patch.object(HoldableOrderHoldTarget, "filter_holdable", holdable):
            result = retry_failed_hold(hold.pk, staff_member)

        assert result.status == PlacementStatus.REFUSED and result.refusal == refusal
        assert fake_stripe.calls == []
        hold = reload(hold)
        assert hold.status == CardHold.Status.FAILED and hold.retry_count == 0

    def test_a_deleted_target_is_refused(self, holder, fake_stripe, staff_member) -> None:
        hold = failed(holder)
        hold.target.delete()

        assert retry_failed_hold(hold.pk, staff_member).refusal == RetryRefusal.NOT_HOLDABLE
        assert fake_stripe.calls == []

    def test_an_unregistered_target_is_refused(
        self, holder, fake_stripe, staff_member, settings
    ) -> None:
        hold = failed(holder)
        settings.BASEAPP_PAYMENTS_CARD_HOLD_TARGETS = {}

        assert retry_failed_hold(hold.pk, staff_member).refusal == RetryRefusal.NOT_HOLDABLE
        assert fake_stripe.calls == []

    def test_a_target_gone_under_the_lock_is_refused(
        self, holder, fake_stripe, staff_member
    ) -> None:
        hold = failed(holder)
        target_pk = hold.target.pk

        def gone(self, pk) -> None:
            return None

        with patch("testproject.testapp.card_holds.HoldableOrderHoldTarget.lock", gone):
            result = retry_failed_hold(hold.pk, staff_member)

        assert result.refusal == RetryRefusal.NOT_HOLDABLE
        assert HoldableOrder.objects.filter(pk=target_pk).exists()
        assert fake_stripe.calls == []

    def test_without_a_stripe_key_nothing_happens(self, holder, no_stripe_key) -> None:
        hold = failed(holder)

        result = retry_failed_hold(hold.pk, None)

        assert result.refusal == RetryRefusal.UNAVAILABLE
        assert reload(hold).retry_count == 0

    def test_a_row_changed_between_the_read_and_the_lock_is_not_retried(
        self, holder, fake_stripe, staff_member
    ) -> None:
        hold = failed(holder)
        real = holds._lock_target_and_hold

        def kept_meanwhile(seen: Any, adapter: Any, **filters: Any) -> Any:
            CardHold.objects.filter(pk=seen.pk).update(kept_at=timezone.now())
            return real(seen, adapter, **filters)

        with patch.object(holds, "_lock_target_and_hold", side_effect=kept_meanwhile):
            result = retry_failed_hold(hold.pk, staff_member)

        assert result.refusal == RetryRefusal.NOT_FAILED
        assert fake_stripe.calls == []

    def test_a_claim_whose_update_matches_nothing_is_not_retried(
        self, holder, fake_stripe, staff_member
    ) -> None:
        """The conditional UPDATE is the claim: under the lock it always matches, but it
        never writes over a row that isn't an undecided failed one."""
        hold = failed(holder)
        real = holds._write_retry_claim

        def raced(hold: Any, *args: Any) -> Any:
            CardHold.objects.filter(pk=hold.pk).update(retry_count=1)
            return real(hold, *args)

        with patch.object(holds, "_write_retry_claim", side_effect=raced):
            result = retry_failed_hold(hold.pk, staff_member)

        assert result.refusal == RetryRefusal.NOT_FAILED
        assert fake_stripe.calls == []


class TestNoAnswer:
    @pytest.mark.parametrize("error", [connection_error, api_error], ids=["conn", "5xx"])
    def test_no_answer_is_in_progress_and_nobody_is_told(
        self, holder, fake_stripe, staff_member, signals, mailoutbox, error
    ) -> None:
        hold = failed(holder)
        fake_stripe.fail_next("PaymentIntent.create", error())

        result = retry_failed_hold(hold.pk, staff_member)

        assert result.status == PlacementStatus.IN_PROGRESS and result.refusal is None
        hold = reload(hold)
        assert hold.status == CardHold.Status.SCHEDULED
        assert hold.placement_key and hold.placement_claimed_at is None
        assert hold.failed_at is not None  # until the retry is authorized
        assert retries_left(hold) is None
        assert signals["failed"].sent == [] and mailoutbox == []

    def test_the_sweep_then_replays_the_same_key_and_settles_it(
        self, holder, fake_stripe, staff_member
    ) -> None:
        hold = failed(holder)
        fake_stripe.fail_next("PaymentIntent.create", connection_error())
        retry_failed_hold(hold.pk, staff_member)

        sweep_card_holds()  # deferral off: it still settles a placement already sent

        first, second = creates(fake_stripe)
        assert first["idempotency_key"] == second["idempotency_key"]
        hold = reload(hold)
        assert hold.status == CardHold.Status.AUTHORIZED
        assert hold.failed_at is None and hold.failure_code == ""
        assert hold.retry_count == 1

    def test_a_webhook_for_the_authorization_behind_a_lost_answer_settles_it(
        self, holder, fake_stripe, staff_member
    ) -> None:
        hold = failed(holder)
        fake_stripe.fail_behind_next(connection_error())
        assert retry_failed_hold(hold.pk, staff_member).status == PlacementStatus.IN_PROGRESS
        (payment_intent_id,) = fake_stripe.intents

        assert reconcile_payment_intent(hold.pk, payment_intent_id) == "settled"

        hold = reload(hold)
        assert hold.status == CardHold.Status.AUTHORIZED
        assert hold.stripe_payment_intent_id == payment_intent_id
        assert hold.failed_at is None

    def test_a_late_webhook_for_the_failed_placement_never_settles_the_retry(
        self, holder, fake_stripe, staff_member
    ) -> None:
        hold = failed_by_the_sweep(holder, fake_stripe)
        (old,) = fake_stripe.intents
        fake_stripe.fail_next("PaymentIntent.create", connection_error())
        assert retry_failed_hold(hold.pk, staff_member).status == PlacementStatus.IN_PROGRESS

        assert reconcile_payment_intent(hold.pk, old) == "ignored"

        hold = reload(hold)
        assert hold.status == CardHold.Status.SCHEDULED and hold.placement_key
        assert hold.previous_payment_intent_ids == [old]

    def test_a_second_click_while_it_is_in_flight_is_in_progress(
        self, holder, fake_stripe, staff_member
    ) -> None:
        hold = failed(holder)
        fake_stripe.fail_next("PaymentIntent.create", connection_error())
        retry_failed_hold(hold.pk, staff_member)

        result = retry_failed_hold(hold.pk, staff_member)

        assert result.status == PlacementStatus.IN_PROGRESS and result.refusal is None
        assert len(creates(fake_stripe)) == 1
        assert reload(hold).retry_count == 1

    def test_while_in_flight_reschedule_and_capture_wait_and_keep_and_cancel_refuse(
        self, holder, fake_stripe, staff_member
    ) -> None:
        hold = failed(holder)
        fake_stripe.fail_next("PaymentIntent.create", connection_error())
        retry_failed_hold(hold.pk, staff_member)

        with override_config(CARD_HOLDS_DEFERRAL_ENABLED=True):
            assert reschedule_hold(hold.pk).status == PlacementStatus.IN_PROGRESS
        assert capture(hold.pk, 10_000, charge=lambda **kw: None).status == (
            CaptureStatus.IN_PROGRESS
        )
        assert keep_failed_hold(hold.pk, staff_member) is False
        assert cancel_failed_hold(hold.pk, staff_member) is False
        assert len(creates(fake_stripe)) == 1


def on_day(day: datetime.date) -> Any:
    """Today, as the holds module and the sweep read it, is ``day``."""
    return patch.object(timezone, "localdate", return_value=day)


class TestARetryOutsideTheWindow:
    """The target's date moved out past the window after the failure: a retry now
    would lapse before the date, so the hold is scheduled again and the sweep places it
    on its new ``hold_on``."""

    def moved_out(self, holder, fake_stripe) -> Any:
        hold = failed_by_the_sweep(holder, fake_stripe)
        HoldableOrder.objects.filter(pk=hold.target.pk).update(target_date=days(21))
        return hold

    def test_it_is_scheduled_for_the_new_day_without_calling_stripe(
        self, holder, fake_stripe, staff_member, signals, django_capture_on_commit_callbacks
    ) -> None:
        hold = self.moved_out(holder, fake_stripe)
        (old,) = fake_stripe.intents
        calls = len(fake_stripe.calls)

        with override_config(CARD_HOLDS_DEFERRAL_ENABLED=True):
            with django_capture_on_commit_callbacks(execute=True):
                result = retry_failed_hold(hold.pk, staff_member)

        assert result.status == PlacementStatus.SCHEDULED and result.refusal is None
        assert result.hold.pk == hold.pk and result.target == hold.target
        assert len(fake_stripe.calls) == calls
        hold = reload(hold)
        assert hold.status == CardHold.Status.SCHEDULED
        assert hold.hold_on == days(21 - 4)  # the default window
        assert hold.failed_at is None and hold.failure_code == ""
        assert hold.placement_key == "" and hold.placement_amount_cents is None
        assert hold.placement_claimed_at is None and hold.placement_sent_at is None
        assert hold.stripe_payment_intent_id is None
        assert hold.previous_payment_intent_ids == [old]
        assert hold.placement_generation == 1
        assert hold.retry_count == 1 and hold.last_retried_by == staff_member
        assert retries_left(hold) is None
        assert [sent["hold"].pk for sent in signals["retried"].sent] == [hold.pk]
        # A scheduled hold like any other: the failure is no longer staff's to decide.
        assert keep_failed_hold(hold.pk, staff_member) is False
        assert retry_failed_hold(hold.pk, staff_member).refusal == RetryRefusal.NOT_FAILED

    def test_the_sweep_places_it_on_the_day_with_a_new_key(
        self, holder, fake_stripe, staff_member
    ) -> None:
        hold = self.moved_out(holder, fake_stripe)
        failed_key = creates(fake_stripe)[0]["idempotency_key"]
        with override_config(CARD_HOLDS_DEFERRAL_ENABLED=True):
            retry_failed_hold(hold.pk, staff_member)
            the_day = reload(hold).hold_on

            with on_day(the_day - datetime.timedelta(days=1)):
                sweep_card_holds()
            assert len(creates(fake_stripe)) == 1  # not due yet

            with on_day(the_day):
                sweep_card_holds()

        first, placed = creates(fake_stripe)
        assert placed["idempotency_key"] != failed_key
        assert placed["off_session"] is True and placed["payment_method"] == "pm_visa"
        hold = reload(hold)
        assert hold.status == CardHold.Status.AUTHORIZED
        assert hold.stripe_payment_intent_id == fake_stripe.live_authorizations()[0]
        assert hold.retry_count == 1

    def test_a_failure_on_the_day_counts_down_and_tells_staff(
        self,
        holder,
        fake_stripe,
        staff_member,
        signals,
        mailoutbox,
        django_capture_on_commit_callbacks,
    ) -> None:
        hold = self.moved_out(holder, fake_stripe)
        with override_config(CARD_HOLDS_DEFERRAL_ENABLED=True):
            retry_failed_hold(hold.pk, staff_member)
            fake_stripe.next_outcome = ["insufficient_funds"]
            with on_day(reload(hold).hold_on):
                with django_capture_on_commit_callbacks(execute=True):
                    sweep_card_holds()

        hold = reload(hold)
        assert hold.status == CardHold.Status.FAILED
        assert hold.failure_code == "insufficient_funds" and hold.failed_at is not None
        assert hold.retry_count == 1 and retries_left(hold) == 2
        assert len(signals["failed"].sent) == 1
        (mail,) = mailoutbox
        assert mail.to == ["ops@example.com"]
        assert "insufficient_funds" in mail.body
        # Staff may retry it again, and it waits for its day again.
        with override_config(CARD_HOLDS_DEFERRAL_ENABLED=True):
            again = retry_failed_hold(hold.pk, staff_member)
        assert again.status == PlacementStatus.SCHEDULED
        assert reload(hold).retry_count == 2

    def test_inside_the_window_it_is_placed_now(self, holder, fake_stripe, staff_member) -> None:
        hold = failed(holder)

        with override_config(CARD_HOLDS_DEFERRAL_ENABLED=True):
            result = retry_failed_hold(hold.pk, staff_member)

        assert result.status == PlacementStatus.PLACED
        assert len(creates(fake_stripe)) == 1

    def test_with_deferral_off_it_is_placed_now_as_at_checkout(
        self, holder, fake_stripe, staff_member
    ) -> None:
        hold = failed(holder, target_date=21)

        result = retry_failed_hold(hold.pk, staff_member)

        assert result.status == PlacementStatus.PLACED
        assert len(creates(fake_stripe)) == 1

    def test_a_target_priced_at_nothing_is_refused(self, holder, fake_stripe, staff_member) -> None:
        hold = failed(holder, target_date=21)
        HoldableOrder.objects.filter(pk=hold.target.pk).update(amount_cents=0)

        with override_config(CARD_HOLDS_DEFERRAL_ENABLED=True):
            result = retry_failed_hold(hold.pk, staff_member)

        assert result.refusal == RetryRefusal.NOT_HOLDABLE
        hold = reload(hold)
        assert hold.status == CardHold.Status.FAILED and hold.retry_count == 0


# --- The mutation ---------------------------------------------------------------------

RETRY = """
    mutation($input: CardHoldRetryInput!) {
        cardHoldRetry(input: $input) {
            cardHold { id status failureReason retriesLeft kept }
            errors { field messages }
        }
    }
"""


def run(user: Any, hold_id: str) -> Any:
    from testproject.graphql import schema

    request = RequestFactory().post("/graphql")
    request.user = user or AnonymousUser()
    return schema.execute(RETRY, variable_values={"input": {"id": hold_id}}, context_value=request)


@pytest.fixture
def decider(db) -> Any:
    """Staff granted change_cardhold (and view_cardhold, to read the payload back)."""
    return grant_card_hold_perm(grant_card_hold_perm(UserFactory(is_staff=True)), "view_cardhold")


def error_of(result: Any) -> dict:
    assert result.errors, result.data
    return result.errors[0].extensions


class TestTheMutation:
    def test_a_retry_that_succeeds_answers_authorized(self, holder, fake_stripe, decider) -> None:
        hold = failed(holder)

        result = run(decider, get_obj_relay_id(hold))

        assert result.errors is None, result.errors
        assert result.data["cardHoldRetry"] == {
            "cardHold": {
                "id": get_obj_relay_id(hold),
                "status": "authorized",
                "failureReason": None,
                "retriesLeft": None,
                "kept": False,
            },
            "errors": None,
        }
        assert reload(hold).last_retried_by == decider

    def test_a_retry_that_fails_again_answers_failed_with_one_less_retry(
        self, holder, fake_stripe, decider
    ) -> None:
        hold = failed(holder)
        fake_stripe.next_outcome = ["insufficient_funds"]

        result = run(decider, get_obj_relay_id(hold))

        assert result.errors is None, result.errors
        assert result.data["cardHoldRetry"]["cardHold"]["status"] == "failed"
        assert result.data["cardHoldRetry"]["cardHold"]["failureReason"] == "insufficient_funds"
        assert result.data["cardHoldRetry"]["cardHold"]["retriesLeft"] == 2

    def test_no_answer_answers_pending_to_staff(self, holder, fake_stripe, decider) -> None:
        hold = failed(holder)
        fake_stripe.fail_next("PaymentIntent.create", connection_error())

        result = run(decider, get_obj_relay_id(hold))

        assert result.errors is None, result.errors
        assert result.data["cardHoldRetry"]["cardHold"]["status"] == "pending"
        assert result.data["cardHoldRetry"]["cardHold"]["retriesLeft"] is None
        # A second click while it's in flight answers the same, places nothing more.
        again = run(decider, get_obj_relay_id(hold))
        assert again.data["cardHoldRetry"]["cardHold"]["status"] == "pending"
        assert len(creates(fake_stripe)) == 1

    def test_a_target_moved_past_the_window_answers_scheduled_with_its_day(
        self, holder, fake_stripe, decider
    ) -> None:
        from testproject.graphql import schema

        hold = failed(holder, target_date=21)
        request = RequestFactory().post("/graphql")
        request.user = decider
        mutation = """
            mutation($input: CardHoldRetryInput!) {
                cardHoldRetry(input: $input) { cardHold { status holdOn retriesLeft } }
            }
        """

        with override_config(CARD_HOLDS_DEFERRAL_ENABLED=True):
            result = schema.execute(
                mutation,
                variable_values={"input": {"id": get_obj_relay_id(hold)}},
                context_value=request,
            )

        assert result.errors is None, result.errors
        assert result.data["cardHoldRetry"]["cardHold"] == {
            "status": "scheduled",
            "holdOn": days(17).isoformat(),
            "retriesLeft": None,
        }
        assert creates(fake_stripe) == []

    @pytest.mark.parametrize(
        "setup, reason",
        [
            ("kept", "not_failed"),
            ("cancelled", "not_failed"),
            ("authorized", "not_failed"),
            ("no_retries", "no_retries_left"),
            ("date_passed", "date_passed"),
            ("target_cancelled", "not_holdable"),
        ],
    )
    def test_refusals_are_invalid_action_errors_with_a_reason(
        self, holder, fake_stripe, decider, setup, reason
    ) -> None:
        hold = failed(holder)
        if setup == "kept":
            keep_failed_hold(hold.pk, decider)
        elif setup == "cancelled":
            cancel_failed_hold(hold.pk, decider)
        elif setup == "authorized":
            CardHold.objects.filter(pk=hold.pk).update(status=CardHold.Status.AUTHORIZED)
        elif setup == "no_retries":
            CardHold.objects.filter(pk=hold.pk).update(retry_count=3)
        elif setup == "date_passed":
            HoldableOrder.objects.filter(pk=hold.target.pk).update(target_date=days(0))
        else:
            HoldableOrder.objects.filter(pk=hold.target.pk).update(status="cancelled")

        result = run(decider, get_obj_relay_id(hold))

        assert error_of(result) == {"code": "invalid_action", "reason": reason}
        assert str(result.errors[0].message)
        assert creates(fake_stripe) == []

    def test_without_a_stripe_key_it_is_unavailable(self, holder, decider, no_stripe_key) -> None:
        result = run(decider, get_obj_relay_id(failed(holder)))

        assert error_of(result) == {"code": "invalid_action", "reason": "unavailable"}

    def test_the_customer_cant_retry_their_own_hold(self, holder, fake_stripe) -> None:
        hold = failed(holder)

        assert error_of(run(holder, get_obj_relay_id(hold)))["code"] == "permission_required"
        assert reload(hold).retry_count == 0 and fake_stripe.calls == []

    def test_staff_status_or_view_cardhold_alone_isnt_enough(self, holder, fake_stripe) -> None:
        hold = failed(holder)
        viewer = grant_card_hold_perm(UserFactory(is_staff=True), "view_cardhold")

        for user in (UserFactory(is_staff=True), viewer):
            assert error_of(run(user, get_obj_relay_id(hold)))["code"] == "permission_required"
        assert fake_stripe.calls == []

    def test_change_cardhold_alone_retries_but_reads_the_hold_as_a_customer(
        self, holder, fake_stripe
    ) -> None:
        hold = failed(holder)
        changer = grant_card_hold_perm(UserFactory(is_staff=True))
        fake_stripe.next_outcome = ["card_declined"]

        result = run(changer, get_obj_relay_id(hold))

        assert result.errors is None, result.errors
        # Without view_cardhold the failure details read as the customer sees them.
        assert result.data["cardHoldRetry"]["cardHold"]["status"] == "scheduled"
        assert result.data["cardHoldRetry"]["cardHold"]["retriesLeft"] is None
        assert reload(hold).retry_count == 1

    def test_a_superuser_may_retry(self, holder, fake_stripe) -> None:
        hold = failed(holder)

        result = run(UserFactory(is_superuser=True, is_staff=True), get_obj_relay_id(hold))

        assert result.errors is None, result.errors
        assert result.data["cardHoldRetry"]["cardHold"]["status"] == "authorized"

    def test_anonymous_is_refused(self, holder, fake_stripe) -> None:
        hold = failed(holder)

        assert run(None, get_obj_relay_id(hold)).errors
        assert reload(hold).retry_count == 0 and fake_stripe.calls == []

    @pytest.mark.parametrize("bad_id", ["not-an-id", "user"])
    def test_a_bad_id_is_refused_like_a_forbidden_one(
        self, holder, fake_stripe, decider, bad_id
    ) -> None:
        relay_id = get_obj_relay_id(holder) if bad_id == "user" else bad_id

        assert error_of(run(decider, relay_id))["code"] == "permission_required"
        assert fake_stripe.calls == []


def test_retries_left_reads_the_limit_when_none_is_given(holder) -> None:
    hold = failed(holder, retry_count=1)

    with override_config(CARD_HOLDS_MAX_RETRIES=5):
        assert retries_left(hold) == 4
    assert retries_left(hold, limit=1) == 0
