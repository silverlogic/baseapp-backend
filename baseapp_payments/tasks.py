"""Payments background work. Card holds: the release, placement, reschedule and
reconcile tasks, and the 15-minute sweep.

Every task is a no-op without a Stripe key or a concrete card hold model, and retries
are bounded.
"""

import datetime
import logging
from typing import Any

from celery import shared_task
from django.contrib.contenttypes.models import ContentType
from django.db.models import Q, Subquery
from django.utils import timezone

from .models import card_holds_enabled, get_card_hold_model
from .utils import RETRYABLE_STRIPE_ERRORS, stripe_configured

logger = logging.getLogger(__name__)

RELEASE_MAX_RETRIES = 12
MAX_RETRY_COUNTDOWN = 1500
# A hold with no target this long after it was created was abandoned (the browser
# closed mid-authentication, a crash between authorizing and placing).
ORPHAN_AFTER = datetime.timedelta(minutes=30)
# A release task stamped this recently is still working (each attempt re-stamps, and the
# longest wait between attempts is MAX_RETRY_COUNTDOWN): the sweep leaves it alone.
RELEASE_IN_FLIGHT = datetime.timedelta(seconds=MAX_RETRY_COUNTDOWN + 5 * 60)
# A hold released this recently still has its own release task queued: not re-driven yet.
RELEASE_GRACE = datetime.timedelta(minutes=15)
# An unconfirmed release with no known expiry (never authorized) is re-driven this long,
# Stripe's longest online authorization.
UNCONFIRMED_WITHOUT_EXPIRY = datetime.timedelta(days=7)


def backoff_countdown(retries: int) -> int:
    """Exponential backoff from one minute, capped at 1500 s.

    Celery holds a countdown task un-acked in the worker until it runs; RabbitMQ's default
    consumer timeout is 30 minutes, past which the message is redelivered as a second,
    concurrent run. The cap stays under it.
    """
    return min(60 * 2**retries, MAX_RETRY_COUNTDOWN)


def _active() -> bool:
    if not card_holds_enabled():
        return False
    if not stripe_configured():
        logger.debug("Stripe isn't configured; card hold task skipped")
        return False
    return True


def _enqueue(task: Any, card_hold_id: int, **kwargs: Any) -> bool:
    """Queue one task for one hold; a broker error is logged and skipped, so one failure
    never stops the rest of a sweep. The hold still needs it, so a later sweep queues it
    again."""
    try:
        task.delay(card_hold_id, **kwargs)
    except Exception:
        logger.exception("Could not queue %s for card hold %s", task.name, card_hold_id)
        return False
    return True


def _enqueue_release(card_hold_id: int, **kwargs: Any) -> bool:
    return _enqueue(release_card_hold, card_hold_id, **kwargs)


@shared_task(bind=True)
def release_card_hold(
    self,
    card_hold_id: int,
    claimed: bool = False,
    card_released: bool = False,
    payment_intent_id: str | None = None,
) -> None:
    """Cancel a hold's PaymentIntent in Stripe and mark it released (see ``release``).

    Each attempt stamps the hold as in flight, so the sweep doesn't queue a duplicate
    while this task works or waits to retry. Retries connection, API and rate-limit
    errors with exponential backoff, up to 12 times; after that, and whenever the task
    ends, the stamp is cleared, and the sweep re-drives the hold if it still needs it:
    an open hold on a cancelled target, or a ``released`` one Stripe hasn't confirmed.
    """
    if not _active():
        return
    from .holds import clear_release_in_flight, mark_release_in_flight, release

    mark_release_in_flight(card_hold_id)
    try:
        release(
            card_hold_id,
            claimed=claimed,
            card_released=card_released,
            payment_intent_id=payment_intent_id,
        )
    except RETRYABLE_STRIPE_ERRORS as error:
        if self.request.retries >= RELEASE_MAX_RETRIES:
            logger.error("Gave up releasing card hold %s; the sweep will retry", card_hold_id)
            clear_release_in_flight(card_hold_id)
            return
        raise self.retry(
            exc=error,
            args=[card_hold_id],
            kwargs={
                "claimed": claimed,
                "card_released": card_released,
                "payment_intent_id": payment_intent_id,
            },
            countdown=backoff_countdown(self.request.retries),
            max_retries=RELEASE_MAX_RETRIES,
        )
    except Exception:
        clear_release_in_flight(card_hold_id)
        raise
    clear_release_in_flight(card_hold_id)


@shared_task
def place_card_hold(card_hold_id: int) -> None:
    """Place one due scheduled hold off-session (``holds.place_scheduled``). Not retried
    here: the hold's claim makes a redelivered or duplicate task a no-op, and a hold
    left scheduled (no usable answer from Stripe) is queued again by the next sweep,
    which retries it with the same idempotency key."""
    if not _active():
        return
    from .holds import place_scheduled

    place_scheduled(card_hold_id)


@shared_task(bind=True)
def reschedule_card_hold(self, card_hold_id: int) -> None:
    """Follow a change of the hold's target's date (``holds.reschedule_hold``), or put a
    hold released ``rescheduled`` / ``not_holdable`` back to ``scheduled``.

    Retried with exponential backoff, up to 12 times, on Stripe's transient errors and
    while a capture or placement of the hold is under way. A hold released
    ``rescheduled`` and left there is picked up by the sweep.
    """
    if not _active():
        return
    from .holds import PlacementStatus, reschedule_hold

    try:
        result = reschedule_hold(card_hold_id)
    except RETRYABLE_STRIPE_ERRORS as error:
        result, retry_error = None, error
    else:
        retry_error = None
    if retry_error is None and (result is None or result.status != PlacementStatus.IN_PROGRESS):
        return
    if self.request.retries >= RELEASE_MAX_RETRIES:
        logger.error("Gave up rescheduling card hold %s", card_hold_id)
        return
    raise self.retry(
        exc=retry_error,
        args=[card_hold_id],
        countdown=backoff_countdown(self.request.retries),
        max_retries=RELEASE_MAX_RETRIES,
    )


@shared_task(bind=True)
def reconcile_card_hold(self, card_hold_id: int, payment_intent_id: str | None = None) -> None:
    """Reconcile a hold with Stripe.

    With ``payment_intent_id`` (queued by the Stripe webhook for a PaymentIntent whose
    metadata names this hold): record what that PaymentIntent is now
    (``holds.reconcile_payment_intent``). Without (queued by the sweep): close an
    on-session create that got no usable answer for 23 hours, cancelling what a lookup
    finds (``holds.reconcile_stale_send``). Stripe's transient errors are retried with
    exponential backoff, up to 12 times.
    """
    if not _active():
        return
    from .holds import reconcile_payment_intent, reconcile_stale_send

    try:
        if payment_intent_id is None:
            reconcile_stale_send(card_hold_id)
        else:
            reconcile_payment_intent(card_hold_id, payment_intent_id)
    except RETRYABLE_STRIPE_ERRORS as error:
        if self.request.retries >= RELEASE_MAX_RETRIES:
            logger.error("Gave up reconciling card hold %s with Stripe", card_hold_id)
            return
        raise self.retry(
            exc=error,
            args=[card_hold_id],
            kwargs={"payment_intent_id": payment_intent_id},
            countdown=backoff_countdown(self.request.retries),
            max_retries=RELEASE_MAX_RETRIES,
        )


@shared_task
def sweep_card_holds() -> None:
    """Release what nothing else will (Celery beat, every 15 minutes):

    - open holds with no target, created over 30 minutes ago, each claimed first so a
      hold linked since the listing is skipped;
    - ``released`` holds whose cancel Stripe hasn't confirmed (a task that ran out of
      retries, or that the broker never got), until the authorization expires;
    - open holds whose target is cancelled (a release that ran out of retries);
    - open holds whose target is done with the card, unless a charge may be in flight
      (re-checked under the lock by the release task);
    - stray authorizations (a lost answer's, found by a webhook or a lookup) whose
      cancel Stripe hasn't confirmed.

    An on-session create whose answer was lost (a ``pending`` row with a
    ``placement_key`` and no PaymentIntent) isn't an orphan: once its key is 23 hours
    old (``PLACEMENT_KEY_TTL``) it is queued to ``reconcile_card_hold`` instead.

    Scheduled holds and saved cards count as open here: on a cancelled target, or one
    done with the card, they are released with no Stripe call. Whatever the setting, it
    queues ``place_card_hold`` for every scheduled hold whose last placement had no
    usable answer (``placement_key``), so Stripe replays it with the same key, including
    one whose target was deleted since (what comes back is cancelled). With
    ``CARD_HOLDS_DEFERRAL_ENABLED`` it also queues ``place_card_hold`` for every
    scheduled hold whose day has come and whose target is still holdable
    (``filter_holdable``), unless a live claim is on it. Whatever the setting, it queues
    ``reschedule_card_hold`` for a hold released ``rescheduled`` or ``not_holdable`` and
    left there, once its cancel is confirmed, so it goes back to ``scheduled`` (with the
    setting off it isn't placed then: ``capture()`` charges it on the date).

    A hold a release task is working on (stamped within the last 30 minutes) is
    skipped, so retries waiting out their backoff aren't duplicated every 15 minutes.
    A broker error queuing one hold doesn't stop the others.
    """
    if not _active():
        return
    from .hold_targets import deferral_enabled, get_targets
    from .holds import PLACEMENT_CLAIM_TIMEOUT, PLACEMENT_KEY_TTL, claim_orphan

    now = timezone.now()
    CardHold = get_card_hold_model()
    not_in_flight = CardHold.objects.filter(
        Q(release_requested_at__isnull=True) | Q(release_requested_at__lt=now - RELEASE_IN_FLIGHT)
    )
    open_holds = not_in_flight.filter(status__in=CardHold.OPEN_STATUSES)
    # A scheduled hold being placed is settled by its placement, not released here.
    releasable = not_in_flight.filter(
        Q(status__in=CardHold.OPEN_STATUSES)
        | Q(status__in=CardHold.UNPLACED_STATUSES, placement_key="")
    )

    # A row whose create is unanswered is reconciled below, never released blind.
    orphaned = (
        open_holds.filter(target_document__isnull=True, created__lt=now - ORPHAN_AFTER)
        .filter(Q(placement_key="") | Q(stripe_payment_intent_id__isnull=False))
        .values_list("pk", "stripe_payment_intent_id")
    )
    for hold_id, payment_intent_id in list(orphaned):
        if claim_orphan(hold_id):
            _enqueue_release(hold_id, claimed=True, payment_intent_id=payment_intent_id)

    unconfirmed = (
        not_in_flight.filter(
            status=CardHold.Status.RELEASED,
            release_confirmed_at__isnull=True,
            stripe_payment_intent_id__isnull=False,
            modified__lt=now - RELEASE_GRACE,
        )
        .filter(
            Q(expires_at__gt=now)
            | Q(expires_at__isnull=True, created__gt=now - UNCONFIRMED_WITHOUT_EXPIRY)
        )
        .values_list("pk", "stripe_payment_intent_id")
    )
    for hold_id, payment_intent_id in list(unconfirmed):
        _enqueue_release(hold_id, claimed=True, payment_intent_id=payment_intent_id)

    strays = (
        not_in_flight.exclude(stray_payment_intent_ids=[])
        .filter(modified__lt=now - RELEASE_GRACE)
        .values_list("pk", "stray_payment_intent_ids")
    )
    for hold_id, payment_intent_ids in list(strays):
        for payment_intent_id in payment_intent_ids:
            _enqueue_release(hold_id, claimed=True, payment_intent_id=payment_intent_id)

    stale_sends = (
        CardHold.objects.filter(
            status=CardHold.Status.PENDING,
            target_document__isnull=True,
            stripe_payment_intent_id__isnull=True,
            placement_sent_at__lt=now - PLACEMENT_KEY_TTL,
        )
        .exclude(placement_key="")
        .filter(
            Q(placement_claimed_at__isnull=True)
            | Q(placement_claimed_at__lt=now - PLACEMENT_CLAIM_TIMEOUT)
        )
        .values_list("pk", flat=True)
    )
    for hold_id in list(stale_sends):
        _enqueue(reconcile_card_hold, hold_id)

    for model, adapter in get_targets().items():
        everything = model._default_manager.all()
        on_model = releasable.filter(
            target_document__content_type=ContentType.objects.get_for_model(model)
        )
        cancelled = on_model.filter(
            target_document__object_id__in=Subquery(
                adapter.filter_cancelled(everything).values("pk")
            )
        ).values_list("pk", flat=True)
        cancelled_ids = list(cancelled)
        for hold_id in cancelled_ids:
            _enqueue_release(hold_id)

        card_released = (
            on_model.filter(
                target_document__object_id__in=Subquery(
                    adapter.filter_card_released(everything).values("pk")
                )
            )
            .exclude(pk__in=cancelled_ids)
            .values_list("pk", "target_document__object_id")
        )
        rows = list(card_released)
        targets = model._default_manager.in_bulk([object_id for _pk, object_id in rows])
        for hold_id, object_id in rows:
            target = targets.get(object_id)
            if target is not None and adapter.charge_may_be_in_flight(target):
                continue
            _enqueue_release(hold_id, card_released=True)

    unclaimed = CardHold.objects.filter(status=CardHold.Status.SCHEDULED).filter(
        Q(placement_claimed_at__isnull=True)
        | Q(placement_claimed_at__lt=now - PLACEMENT_CLAIM_TIMEOUT)
    )
    # Finishing a placement already sent to Stripe is settling it, not placing anew, so
    # it runs with deferral off too, and for a hold whose target is gone (unlinked).
    unsettled = unclaimed.exclude(placement_key="").values_list("pk", flat=True)
    for hold_id in list(unsettled):
        _enqueue(place_card_hold, hold_id)

    if deferral_enabled():
        _sweep_scheduled(CardHold, unclaimed.filter(placement_key=""))

    # Back to scheduled whatever the setting: the flag stops new placements only, and
    # with it off the row then waits for capture() to charge it.
    stranded = CardHold.objects.filter(
        status=CardHold.Status.RELEASED,
        release_reason__in=CardHold.BACK_TO_SCHEDULED_REASONS,
        release_confirmed_at__isnull=False,
        target_document__isnull=False,
    ).values_list("pk", flat=True)
    for hold_id in list(stranded):
        _enqueue(reschedule_card_hold, hold_id)


def _sweep_scheduled(CardHold: Any, unclaimed: Any) -> None:
    """Queue the placement of due scheduled holds."""
    from .hold_targets import get_targets

    today = timezone.localdate()
    for model, adapter in get_targets().items():
        everything = model._default_manager.all()
        holdable = adapter.filter_holdable(everything).exclude(
            pk__in=Subquery(adapter.filter_cancelled(everything).values("pk"))
        )
        due = unclaimed.filter(
            target_document__content_type=ContentType.objects.get_for_model(model),
            hold_on__lte=today,
            target_document__object_id__in=Subquery(holdable.values("pk")),
        ).values_list("pk", flat=True)
        for hold_id in list(due):
            _enqueue(place_card_hold, hold_id)
