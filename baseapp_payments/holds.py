"""Placing, releasing and capturing card holds.

The flow a project's create mutation drives, while the customer is present:

1. :func:`authorize_on_session` (first pass): returns what an attempt already ended in,
   else reads the card from Stripe, prices the target, authorizes a manual-capture
   PaymentIntent and records a ``pending`` hold. When Stripe needs authentication
   (3D Secure) it returns ``requires_action`` and a client secret.
2. :func:`complete_on_session` (second pass, after authentication): checks the
   PaymentIntent is this user's attempt, then links it.

Linking happens under the hold's row lock with no Stripe call inside: the project's
``link`` callable creates (or the caller names) the target, the target is re-checked and
re-priced through its adapter, and the hold is linked and ``authorized``. Any refusal
releases the still-unlinked hold; a linked hold is never cancelled by placing.

Both passes must run outside any transaction (:class:`CardHoldInTransaction`): the
pending hold row has to be committed the moment the PaymentIntent exists.

Only a target charged in the future takes a hold: one dated today, in the past or not at
all answers ``charge_now`` before anything else, and the project charges it directly.
A target whose adapter doesn't use holds (``uses_holds = False``) authorizes nothing:
its card is saved with a SetupIntent (a ``saved`` row) and :func:`capture` charges it
on the date, once.

A target dated further out than the window (``CARD_HOLDS_DEFERRAL_ENABLED``) gets a
``scheduled`` hold instead: the first pass saves the card with an off-session SetupIntent
(:func:`complete_setup_on_session` is its second pass) and authorizes nothing. The sweep
places it on its ``hold_on`` day (:func:`place_scheduled`), off-session; a refusal is
final (``failed``) and staff decide it (:func:`keep_failed_hold`,
:func:`cancel_failed_hold`). :func:`reschedule` follows a change of the target's date.

Lock order, everywhere: the target's adapter ``lock()`` first, then the hold. Stripe is
never called while a row lock is held. See "Card holds" in the package README.
"""

import datetime
import enum
import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from decimal import ROUND_CEILING, Decimal
from typing import TYPE_CHECKING, Any

import stripe
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.db import IntegrityError, transaction
from django.db.models import F, Model, Q, Subquery
from django.utils import timezone

from baseapp_core.models import DocumentId

from . import utils
from .hold_targets import (
    HoldAmountMode,
    HoldTarget,
    deferral_enabled,
    get_targets,
    is_cancelled,
    is_card_released,
    target_for_content_type_id,
    target_for_model,
    window_days_of,
)
from .models import get_card_hold_model
from .plugin import DEFAULT_CARD_HOLD_KEY_PREFIX
from .signals import (
    card_hold_authorized,
    card_hold_failed,
    card_hold_released,
    difference_charge_failed,
    payment_status_changed,
    send_on_commit,
)
from .utils import (
    CONFIGURATION_STRIPE_ERRORS,
    OFF_SESSION_HOLD_EXPIRY_FALLBACK,
    PAYMENT_INTENT_EXPAND,
    RETRYABLE_STRIPE_ERRORS,
    Card,
    cancel_payment_intent_quietly,
    card_of,
    hold_expiry,
    is_idempotent_replay,
    payment_intent_status_of,
    stripe_field,
    stripe_id,
)

if TYPE_CHECKING:
    from django.contrib.auth.base_user import AbstractBaseUser

    from .models import AbstractCardHold

logger = logging.getLogger(__name__)

# Stripe's codes for a capture refused because the authorization is gone.
LAPSED_AUTHORIZATION_CODES = frozenset({"charge_expired_for_capture"})
# ``cancellation_reason`` of a PaymentIntent Stripe cancelled itself when its authorization
# lapsed: ``expired`` from API version 2025-03-31.basil on, ``automatic`` before it (an
# event or object rendered at an older version still says so).
LAPSED_CANCELLATION_REASONS = frozenset({"expired", "automatic"})
# PaymentIntent statuses a second pass can do nothing with: the authorization is over.
TERMINAL_INTENT_STATUSES = frozenset({"canceled", "requires_payment_method"})
# A capture claim older than this belongs to a call that died; another call may take it.
CAPTURE_CLAIM_TIMEOUT = datetime.timedelta(minutes=10)
# The same for the claim of a scheduled hold's off-session placement.
PLACEMENT_CLAIM_TIMEOUT = datetime.timedelta(minutes=10)
# Stripe keeps an idempotency key for 24 hours. A charge claimed longer ago than this and
# never finished is not re-run with its key, which Stripe may have forgotten: it could
# charge a second time. It needs reconciling by hand.
CHARGE_KEY_TTL = datetime.timedelta(hours=23)
# The same for a PaymentIntent create (a placement) with no usable answer: replayed with
# its key only this long after it was first sent (``placement_sent_at``). Past it, Stripe
# may have forgotten the key, and a replay could authorize a second time, so the create
# is reconciled instead (:func:`find_hold_payment_intents`).
PLACEMENT_KEY_TTL = datetime.timedelta(hours=23)
# How far before the first send the list fallback of the lookup reads PaymentIntents.
LOOKUP_MARGIN = datetime.timedelta(hours=1)
# SetupIntent statuses a second pass can do nothing with: the card wasn't saved.
TERMINAL_SETUP_STATUSES = frozenset({"canceled", "requires_payment_method"})
SETUP_INTENT_EXPAND = ["payment_method"]


def _holds() -> type["AbstractCardHold"]:
    return get_card_hold_model()


def key_prefix() -> str:
    """The prefix of every Stripe idempotency key card holds send
    (``BASEAPP_PAYMENTS_CARD_HOLD_KEY_PREFIX``)."""
    configured = getattr(settings, "BASEAPP_PAYMENTS_CARD_HOLD_KEY_PREFIX", None)
    return configured or DEFAULT_CARD_HOLD_KEY_PREFIX


# --- Results ------------------------------------------------------------------------


class PlacementStatus(str, enum.Enum):
    """How a placement attempt ended.

    - ``placed``: the hold is authorized and linked; ``target`` is set.
    - ``scheduled``: the target is placed and its hold will be, off-session, on
      ``hold_on`` (the card is saved; nothing is authorized yet). ``target`` is set.
    - ``card_saved``: the target's adapter doesn't use holds. The target is placed and
      its card saved; nothing is authorized, and :func:`capture` charges it on the date.
      ``target`` is set.
    - ``charge_now``: no hold is needed. The target is charged now (it has no date
      after today), so nothing was saved, authorized or linked: charge it directly,
      while the customer is present.
    - ``requires_action``: Stripe wants authentication; send ``client_secret`` to the page.
    - ``declined``: the card can't be held. Ask for another card (new attempt id).
    - ``in_progress``: this attempt is already being placed. Retry with the same attempt id.
    - ``changed``: the attempt id was reused with different parameters. Renew it and resend.
    - ``amount_changed``: the price the page showed is no longer the price.
    - ``refused``: the project's ``link`` refused (its own validation; see ``errors``), or
      the target can't take a hold (cancelled, done with the card, not holdable, or it
      already has a hold that can't be re-armed).
    """

    PLACED = "placed"
    SCHEDULED = "scheduled"
    CARD_SAVED = "card_saved"
    CHARGE_NOW = "charge_now"
    REQUIRES_ACTION = "requires_action"
    DECLINED = "declined"
    IN_PROGRESS = "in_progress"
    CHANGED = "changed"
    AMOUNT_CHANGED = "amount_changed"
    REFUSED = "refused"


@dataclass
class PlacementResult:
    status: PlacementStatus
    target: Model | None = None
    hold: "AbstractCardHold | None" = None
    client_secret: str | None = None
    intent_type: str | None = None
    errors: Any = None

    @property
    def requires_action(self) -> bool:
        return self.status == PlacementStatus.REQUIRES_ACTION

    @property
    def hold_on(self) -> datetime.date | None:
        """For a ``scheduled`` result: the day the hold will be placed."""
        if self.status != PlacementStatus.SCHEDULED or self.hold is None:
            return None
        return self.hold.hold_on


class HoldRefused(Exception):
    """Raised by a project's ``link`` to refuse placing; rolls back what ``link`` wrote
    and releases the hold. ``errors`` is passed back on the result untouched."""

    def __init__(self, errors: Any = None) -> None:
        super().__init__(errors)
        self.errors = errors


class CardHoldInTransaction(RuntimeError):
    """Placing or capturing was called inside ``transaction.atomic()``.

    The pending hold row must be committed as soon as its PaymentIntent exists, so the
    sweep can release it if the request dies; inside a transaction it would vanish with
    a rollback and leave the authorization unreleasable. A capture's claims (the capture
    and charge claims) must commit before Stripe is called, or they would hold a row
    lock across the Stripe call and vanish with a rollback. Call both from a non-atomic
    view, mutation or task (exclude it from ``ATOMIC_MUTATIONS`` / ``ATOMIC_REQUESTS``).
    """


class _AmountChanged(Exception):
    pass


class _RearmPending(Exception):
    """The target's released hold may still have a live authorization (Stripe hasn't
    confirmed its cancel): it can't be re-armed yet."""


def _ensure_outside_transaction() -> None:
    """Raise :class:`CardHoldInTransaction` when the connection isn't in autocommit mode,
    which is what any ``transaction.atomic()`` block (or ``ATOMIC_REQUESTS``) turns off.

    Uses Django's public ``transaction.get_autocommit()``. A test suite that wraps every
    test in a transaction (pytest-django's ``db``, Django's ``TestCase``) sets
    ``BASEAPP_PAYMENTS_CARD_HOLD_REQUIRE_AUTOCOMMIT = False``, and checks the guard in
    transactional tests (``transaction=True`` / ``TransactionTestCase``) with it on.
    """
    if not getattr(settings, "BASEAPP_PAYMENTS_CARD_HOLD_REQUIRE_AUTOCOMMIT", True):
        return
    if not transaction.get_autocommit():
        raise CardHoldInTransaction(
            "Card hold placement and capture must run outside transaction.atomic();"
            " see CardHoldInTransaction."
        )


# --- Pricing ------------------------------------------------------------------------


def hold_amount_cents(estimated_cents: int, buffer_percent: Decimal) -> int:
    """``ceil(estimated × (1 + buffer / 100))``, in cents."""
    amount = Decimal(estimated_cents) * (Decimal(100) + Decimal(buffer_percent)) / Decimal(100)
    return int(amount.to_integral_value(rounding=ROUND_CEILING))


def price(adapter: HoldTarget, target: Model, card: Card | None) -> tuple[int, Decimal, int]:
    """``(estimated_cents, buffer_percent, amount_cents)`` of ``target`` from its adapter.

    What is held follows the adapter's ``hold_amount_mode``: ``value`` holds the estimate
    alone (any buffer the adapter returns is ignored); ``value_plus_buffer`` adds the
    buffer the adapter returned with the amount, else its ``buffer_percent()`` (which
    defaults to ``CARD_HOLDS_BUFFER_PERCENT``). An adapter that doesn't use holds holds
    nothing: ``amount_cents`` is 0.
    """
    quoted = adapter.hold_amount(target, card)
    if not adapter.uses_holds:
        return quoted.estimated_cents, Decimal(0), 0
    if HoldAmountMode(adapter.hold_amount_mode) == HoldAmountMode.VALUE:
        buffer = Decimal(0)
    elif quoted.buffer_percent is not None:
        buffer = Decimal(quoted.buffer_percent)
    else:
        buffer = Decimal(adapter.buffer_percent())
    return quoted.estimated_cents, buffer, hold_amount_cents(quoted.estimated_cents, buffer)


def charged_later(adapter: HoldTarget, target: Model) -> bool:
    """Whether ``target`` is charged after today, the only case a hold (or a saved card)
    is for. No date, today or a past date: it is charged now, directly."""
    target_date = adapter.target_date(target)
    return target_date is not None and target_date > _today()


def _today() -> datetime.date:
    """Today in the project's time zone: target dates are the project's dates."""
    return timezone.localdate()


def hold_on_for(adapter: HoldTarget, target: Model) -> datetime.date:
    """The day a scheduled hold of ``target`` is placed: its date minus the window, or
    today when it has no date."""
    target_date = adapter.target_date(target)
    if target_date is None:
        return _today()
    return target_date - datetime.timedelta(days=window_days_of(adapter))


def deferred_hold_on(adapter: HoldTarget, target: Model) -> datetime.date | None:
    """When ``target``'s hold should wait (``CARD_HOLDS_DEFERRAL_ENABLED``, and its date
    further out than the window): the day to place it. ``None``: hold it now.

    The date is asked first, so a target without one never reads Constance.
    """
    if adapter.target_date(target) is None or not deferral_enabled():
        return None
    hold_on = hold_on_for(adapter, target)
    return hold_on if hold_on > _today() else None


# --- Reading Stripe ------------------------------------------------------------------


def idempotency_key(user: "AbstractBaseUser", attempt_id: uuid.UUID | str) -> str:
    """The on-session key: one authorization per user and attempt."""
    return f"{key_prefix()}-hold-{user.pk}-{attempt_id}"


def usable_payment_method(payment_method_id: str, stripe_customer_id: str) -> Any | None:
    """The PaymentMethod if it's a card that is unattached or attached to this customer.

    Anything else (another customer's card, not a card, an unknown id) is ``None`` and
    logged. The card is always read from Stripe, never taken from the client.
    Stripe errors other than a refusal of the request (an unknown id) propagate: they
    say nothing about the card.
    """
    try:
        payment_method = utils.get_stripe().PaymentMethod.retrieve(payment_method_id)
    except stripe.InvalidRequestError:
        logger.warning("Could not retrieve PaymentMethod %s", payment_method_id, exc_info=True)
        return None
    owner = stripe_id(stripe_field(payment_method, "customer"))
    if stripe_field(payment_method, "type") != "card" or owner not in (None, stripe_customer_id):
        logger.warning(
            "PaymentMethod %s refused: not a card of customer %s",
            payment_method_id,
            stripe_customer_id,
        )
        return None
    return payment_method


def create_hold_payment_intent(
    *,
    user: "AbstractBaseUser",
    attempt_id: uuid.UUID | str,
    stripe_customer_id: str,
    payment_method: Any,
    amount_cents: int,
    currency: str = "usd",
    metadata: dict[str, str] | None = None,
    card_hold_id: int | None = None,
) -> Any:
    """Authorize ``amount_cents`` on the card with manual capture. Stripe errors propagate.

    A card not yet attached is authorized with ``setup_future_usage=off_session``, so
    Stripe attaches it to the customer only when the authorization succeeds.
    ``card_hold_id`` (the row written before the create) goes into the metadata, so a
    webhook or a lookup can match the PaymentIntent to it even if this answer is lost.
    """
    params: dict[str, Any] = {
        "amount": amount_cents,
        "currency": currency,
        "customer": stripe_customer_id,
        "payment_method": stripe_id(payment_method),
        "payment_method_types": ["card"],
        "capture_method": "manual",
        "confirm": True,
        "use_stripe_sdk": True,
        "metadata": {
            **(metadata or {}),
            "user_id": str(user.pk),
            "attempt_id": str(attempt_id),
            **({"card_hold_id": str(card_hold_id)} if card_hold_id is not None else {}),
        },
        "expand": PAYMENT_INTENT_EXPAND,
        "idempotency_key": idempotency_key(user, attempt_id),
    }
    if stripe_field(payment_method, "customer") is None:
        params["setup_future_usage"] = "off_session"
    return utils.get_stripe().PaymentIntent.create(**params)


def setup_idempotency_key(user: "AbstractBaseUser", attempt_id: uuid.UUID | str) -> str:
    """The key of the SetupIntent that saves the card of a scheduled hold: one per user
    and attempt."""
    return f"{key_prefix()}-setup-{user.pk}-{attempt_id}"


def create_hold_setup_intent(
    *,
    user: "AbstractBaseUser",
    attempt_id: uuid.UUID | str,
    stripe_customer_id: str,
    payment_method: Any,
    metadata: dict[str, str] | None = None,
) -> Any:
    """Save the card for off-session use (``usage=off_session``), attaching it to the
    customer, so its hold can be placed later without them. Stripe errors propagate."""
    return utils.get_stripe().SetupIntent.create(
        customer=stripe_customer_id,
        payment_method=stripe_id(payment_method),
        payment_method_types=["card"],
        usage="off_session",
        confirm=True,
        use_stripe_sdk=True,
        metadata={
            **(metadata or {}),
            "user_id": str(user.pk),
            "attempt_id": str(attempt_id),
        },
        expand=SETUP_INTENT_EXPAND,
        idempotency_key=setup_idempotency_key(user, attempt_id),
    )


def retrieve_setup_intent(setup_intent_id: str) -> Any:
    """The SetupIntent with its PaymentMethod expanded. Stripe errors propagate."""
    return utils.get_stripe().SetupIntent.retrieve(setup_intent_id, expand=SETUP_INTENT_EXPAND)


def retrieve_payment_intent(payment_intent_id: str) -> Any:
    """The PaymentIntent with its charge and PaymentMethod expanded. Stripe errors propagate."""
    return utils.get_stripe().PaymentIntent.retrieve(
        payment_intent_id, expand=PAYMENT_INTENT_EXPAND
    )


# --- Recording ------------------------------------------------------------------------


def _card_fields(card: Card) -> dict[str, Any]:
    return {
        "stripe_payment_method_id": card.payment_method_id,
        "card_brand": card.brand,
        "card_last4": card.last4,
        "card_exp_month": card.exp_month,
        "card_exp_year": card.exp_year,
        "card_funding": card.funding,
        "card_fingerprint": card.fingerprint,
    }


def _intent_fields(
    *,
    user: "AbstractBaseUser",
    attempt_id: uuid.UUID | str,
    stripe_customer_id: str,
    payment_intent: Any,
    payment_method: Any,
) -> dict[str, Any]:
    card = card_of(stripe_field(payment_intent, "payment_method") or payment_method)
    amount = stripe_field(payment_intent, "amount", 0) or 0
    return {
        "customer": user,
        "stripe_customer_id": stripe_customer_id or "",
        "attempt_id": attempt_id,
        "currency": stripe_field(payment_intent, "currency") or "usd",
        **_card_fields(card),
        "estimated_amount_cents": amount,
        "buffer_percent": 0,
        "amount_cents": amount,
    }


def record_pending_hold(
    *,
    user: "AbstractBaseUser",
    attempt_id: uuid.UUID | str,
    stripe_customer_id: str,
    payment_intent: Any,
    payment_method: Any = None,
) -> "AbstractCardHold":
    """The hold row of ``payment_intent``, created ``pending`` if it doesn't exist yet.

    Call it outside a transaction: the row is committed as soon as it is written, so the
    sweep can release it even if the request dies right after. An existing row is left
    as it is (it may already be linked, authorized or released). The card comes from
    the PaymentIntent's own PaymentMethod; ``payment_method`` is only the fallback. The
    amounts are provisional until the hold is linked.

    A PaymentIntent whose metadata names the row written before its create
    (``card_hold_id``, :func:`_begin_send`) is recorded on that row while it still waits
    for its answer; one a webhook recorded first is found by its id.
    """
    CardHold = _holds()
    payment_intent_id = stripe_id(payment_intent)
    existing = CardHold.objects.filter(stripe_payment_intent_id=payment_intent_id).first()
    if existing is not None:
        return existing
    fields = _intent_fields(
        user=user,
        attempt_id=attempt_id,
        stripe_customer_id=stripe_customer_id,
        payment_intent=payment_intent,
        payment_method=payment_method,
    )
    sending_id = str(stripe_field(stripe_field(payment_intent, "metadata"), "card_hold_id") or "")
    if sending_id.isdigit() and _attach_send(int(sending_id), payment_intent_id, fields):
        return CardHold.objects.get(pk=int(sending_id))
    hold, _created = CardHold.objects.get_or_create(
        stripe_payment_intent_id=payment_intent_id, defaults=fields
    )
    return hold


# Cleared once the outcome of a create is recorded, or when it is reconciled.
_CLEARED_SEND = {
    "placement_key": "",
    "placement_amount_cents": None,
    "placement_claimed_at": None,
    "placement_sent_at": None,
}


def _sending(CardHold: Any) -> Any:
    """Rows written before an on-session create whose answer isn't recorded yet."""
    return CardHold.objects.filter(
        status=CardHold.Status.PENDING,
        target_document__isnull=True,
        stripe_payment_intent_id__isnull=True,
    ).exclude(placement_key="")


def _attach_send(card_hold_id: int, payment_intent_id: str, fields: dict[str, Any]) -> bool:
    """Record ``payment_intent_id`` on the row written before its create, if that row
    still waits for it (a conditional UPDATE); whether it did. Card fields the
    PaymentIntent didn't carry keep what the row recorded at the send."""
    CardHold = _holds()
    changes = {key: value for key, value in fields.items() if key not in ("customer", "attempt_id")}
    if not changes.get("card_last4"):
        for key in _card_fields(Card(payment_method_id="")):
            changes.pop(key, None)
    return bool(
        _sending(CardHold)
        .filter(
            pk=card_hold_id,
            customer=fields["customer"],
            attempt_id=fields["attempt_id"],
        )
        .update(
            stripe_payment_intent_id=payment_intent_id,
            **changes,
            **_CLEARED_SEND,
            modified=timezone.now(),
        )
    )


def _begin_send(
    *,
    user: "AbstractBaseUser",
    attempt_id: uuid.UUID | str,
    stripe_customer_id: str,
    payment_method: Any,
    amount_cents: int,
    currency: str,
) -> "AbstractCardHold | None":
    """The attempt's ``pending`` row, written and committed before its PaymentIntent is
    created, so the create's key, amount and first send (``placement_sent_at``) are on
    record and the PaymentIntent's metadata can name the row (``card_hold_id``). A retry
    of the attempt gets the same row, so it sends the same metadata. ``None`` when a
    concurrent pass of the attempt took it in between: retry."""
    CardHold = _holds()
    rows = CardHold.objects.filter(
        customer=user,
        attempt_id=attempt_id,
        status=CardHold.Status.PENDING,
        target_document__isnull=True,
        stripe_setup_intent_id__isnull=True,
    )
    hold = rows.first()
    if hold is not None:
        return hold
    now = timezone.now()
    try:
        with transaction.atomic():
            return CardHold.objects.create(
                customer=user,
                stripe_customer_id=stripe_customer_id or "",
                attempt_id=attempt_id,
                currency=currency,
                **_card_fields(card_of(payment_method)),
                estimated_amount_cents=amount_cents,
                buffer_percent=0,
                amount_cents=amount_cents,
                placement_key=idempotency_key(user, attempt_id),
                placement_amount_cents=amount_cents,
                placement_sent_at=now,
            )
    except IntegrityError:
        # The key's unique constraint: a concurrent pass of this attempt wrote it.
        return rows.first()


def _send_is_stale(hold: "AbstractCardHold") -> bool:
    """A create with no usable answer, first sent longer ago than Stripe surely keeps its
    key (:data:`PLACEMENT_KEY_TTL`): never replayed, reconciled instead."""
    return (
        bool(hold.placement_key)
        and hold.placement_sent_at is not None
        and hold.placement_sent_at < timezone.now() - PLACEMENT_KEY_TTL
    )


def _close_send(card_hold_id: int) -> None:
    """The create of an on-session row was refused for good, or reconciled: the row is
    released (abandoned, confirmed: it carries no PaymentIntent), so its attempt answers
    ``declined`` and the client starts a new one."""
    CardHold = _holds()
    now = timezone.now()
    if (
        _sending(CardHold)
        .filter(pk=card_hold_id)
        .update(
            status=CardHold.Status.RELEASED,
            release_reason=CardHold.ReleaseReason.ABANDONED,
            release_confirmed_at=now,
            **_CLEARED_SEND,
            modified=now,
        )
    ):
        send_on_commit(card_hold_released, hold_id=card_hold_id)


def record_pending_setup(
    *,
    user: "AbstractBaseUser",
    attempt_id: uuid.UUID | str,
    stripe_customer_id: str,
    setup_intent: Any,
    payment_method: Any = None,
    currency: str = "usd",
) -> "AbstractCardHold":
    """The hold row of ``setup_intent`` (a card saved for a scheduled hold), created
    ``pending`` if it doesn't exist yet, like :func:`record_pending_hold`. Nothing is
    authorized, so the amounts stay zero until the hold is linked and scheduled."""
    card = card_of(stripe_field(setup_intent, "payment_method") or payment_method)
    hold, _created = _holds().objects.get_or_create(
        stripe_setup_intent_id=stripe_id(setup_intent),
        defaults={
            "customer": user,
            "stripe_customer_id": stripe_customer_id or "",
            "attempt_id": attempt_id,
            "currency": currency,
            **_card_fields(card),
            "estimated_amount_cents": 0,
            "buffer_percent": 0,
            "amount_cents": 0,
        },
    )
    return hold


def abandon_setup(setup_intent_id: str | None) -> None:
    """Release a hold row that saved a card but never got a target. Nothing is held in
    Stripe (a SetupIntent authorizes nothing), so no Stripe call follows; a linked hold
    is never touched."""
    if not setup_intent_id:
        return
    CardHold = _holds()
    changed = CardHold.objects.filter(
        stripe_setup_intent_id=setup_intent_id,
        target_document__isnull=True,
        status=CardHold.Status.PENDING,
    ).update(
        status=CardHold.Status.RELEASED,
        release_reason=CardHold.ReleaseReason.ABANDONED,
        release_confirmed_at=timezone.now(),
        modified=timezone.now(),
    )
    if changed:
        hold_id = CardHold.objects.filter(stripe_setup_intent_id=setup_intent_id).values_list(
            "pk", flat=True
        )[0]
        send_on_commit(card_hold_released, hold_id=hold_id)


def release_on_commit(
    card_hold_id: int, *, claimed: bool = False, payment_intent_id: str | None = None
) -> None:
    """Once the current transaction commits, release the hold through the task.

    ``claimed``: the caller already marked the unlinked hold ``released`` under its lock,
    so only the Stripe cancel is left. ``payment_intent_id`` pins the release to that
    authorization, so a row re-armed meanwhile never has its new PaymentIntent cancelled.
    The callback is robust: if the broker refuses the task, the commit stands, and the
    sweep re-drives the release (an open hold on a cancelled target, or a ``released``
    hold whose cancel Stripe hasn't confirmed).
    """
    from .tasks import release_card_hold

    transaction.on_commit(
        lambda: release_card_hold.delay(
            card_hold_id, claimed=claimed, payment_intent_id=payment_intent_id
        ),
        robust=True,
    )


def abandon_hold(
    payment_intent_id: str | None,
    *,
    user: "AbstractBaseUser | None" = None,
    attempt_id: uuid.UUID | str | None = None,
    stripe_customer_id: str = "",
    payment_intent: Any = None,
    payment_method: Any = None,
) -> None:
    """Release a hold that never got a target, and cancel its PaymentIntent.

    A linked hold is never touched. With no hold row (the create failed before it was
    recorded) a ``released`` row is written when the user and attempt are known, so a
    replay of that PaymentIntent's creation can never be placed (only ``pending`` holds
    are linked), and so the sweep can re-drive its cancel; the PaymentIntent is then
    cancelled through the task. With neither row nor user it is cancelled directly, once.
    """
    if not payment_intent_id:
        return
    CardHold = _holds()
    with transaction.atomic():
        hold = (
            CardHold.objects.select_for_update()
            .filter(stripe_payment_intent_id=payment_intent_id)
            .first()
        )
        if hold is not None and hold.target_document_id is not None:
            return
        if hold is not None:
            if hold.status in CardHold.OPEN_STATUSES:
                hold.status = CardHold.Status.RELEASED
                hold.release_reason = CardHold.ReleaseReason.ABANDONED
                hold.save(update_fields=["status", "release_reason", "modified"])
                send_on_commit(card_hold_released, hold_id=hold.pk)
            release_on_commit(hold.pk, claimed=True, payment_intent_id=payment_intent_id)
            return
        if user is not None and attempt_id is not None:
            try:
                with transaction.atomic():
                    hold = CardHold.objects.create(
                        stripe_payment_intent_id=payment_intent_id,
                        status=CardHold.Status.RELEASED,
                        release_reason=CardHold.ReleaseReason.ABANDONED,
                        **_intent_fields(
                            user=user,
                            attempt_id=attempt_id,
                            stripe_customer_id=stripe_customer_id,
                            payment_intent=payment_intent,
                            payment_method=payment_method,
                        ),
                    )
            except Exception:
                logger.exception(
                    "Could not record released PaymentIntent %s; cancelling it anyway",
                    payment_intent_id,
                )
            else:
                release_on_commit(hold.pk, claimed=True, payment_intent_id=payment_intent_id)
                return
        transaction.on_commit(lambda: cancel_payment_intent_quietly(payment_intent_id), robust=True)


# --- Placing --------------------------------------------------------------------------


def find_attempt(
    user: "AbstractBaseUser", attempt_id: uuid.UUID | str | None
) -> PlacementResult | None:
    """What this user's attempt already ended in, from its hold rows; ``None`` to go on.

    Checked first, on every pass, before any validation or Stripe call. It answers from
    the database, whatever Stripe still remembers (its idempotency keys last 24 hours),
    so an attempt id stays good for exactly one outcome:

    - a hold linked by this attempt, in any status, or a re-armed hold this attempt
      placed before (``previous_attempt_ids``): ``placed``, with that target
      (``scheduled`` while its hold waits for its day, a ``failed`` one reading the
      same, as the customer sees it; ``card_saved`` for a saved card). A target deleted
      since answers ``declined``;
    - an unlinked ``pending`` hold: ``None``; the attempt is under way (a replayed first
      pass or the second pass carries on with it);
    - any other unlinked hold (declined, refused, abandoned, swept): ``declined``; a new
      attempt id is needed;
    - no row: ``None``.
    """
    if attempt_id is None or not getattr(user, "is_authenticated", False):
        return None
    CardHold = _holds()
    rows = list(
        CardHold.objects.filter(customer=user)
        .filter(Q(attempt_id=attempt_id) | Q(previous_attempt_ids__contains=[str(attempt_id)]))
        .select_related("target_document")
    )
    linked = next((hold for hold in rows if hold.target_document_id is not None), None)
    if linked is not None:
        target = linked.target
        if target is None:
            return PlacementResult(PlacementStatus.DECLINED, hold=linked)
        return PlacementResult(_placed_status(linked), target=target, hold=linked)
    if any(hold.status == CardHold.Status.PENDING for hold in rows):
        return None
    if rows:
        return PlacementResult(PlacementStatus.DECLINED, hold=rows[0])
    return None


def _placed_status(hold: "AbstractCardHold") -> PlacementStatus:
    """What a linked hold answers its attempt: ``scheduled`` while it waits for its day
    (a ``failed`` one reads the same, as the customer sees it), ``card_saved`` for a
    saved card, ``placed`` otherwise."""
    Status = type(hold).Status
    if hold.status in (Status.SCHEDULED, Status.FAILED):
        return PlacementStatus.SCHEDULED
    if hold.status == Status.SAVED:
        return PlacementStatus.CARD_SAVED
    return PlacementStatus.PLACED


PLACED_STATUSES = (PlacementStatus.PLACED, PlacementStatus.SCHEDULED, PlacementStatus.CARD_SAVED)


def find_placed(user: "AbstractBaseUser", attempt_id: uuid.UUID | str | None) -> Model | None:
    """The target this user's attempt placed (its hold authorized or scheduled, or its
    card saved), or ``None`` (see :func:`find_attempt`)."""
    found = find_attempt(user, attempt_id)
    if found is not None and found.status in PLACED_STATUSES:
        return found.target
    return None


def _create_intent(
    create: Callable[[], Any],
    *,
    user: "AbstractBaseUser",
    attempt_id: uuid.UUID | str,
    on_card_error: Callable[[stripe.CardError], None],
) -> tuple[Any, PlacementStatus | None]:
    """Create a PaymentIntent or SetupIntent: ``(intent, None)`` or ``(None, refusal)``.

    A connection error (no response), a Stripe server error (5xx) or a rate limit (429)
    may hide an intent Stripe did make, or be gone a moment later, so the create is
    retried once with the same key, which returns that intent if it exists; failing
    again answers ``in_progress``, and a retry of the attempt (same key) settles it. A
    409 (a concurrent request with the same key) is ``in_progress``; an
    ``IdempotencyError`` (same key, other parameters) is ``changed``. A card error runs
    ``on_card_error`` and declines. A bad or revoked key (``AuthenticationError``,
    ``PermissionError``) says nothing about the card: it is logged as an error and
    answers ``in_progress``, not retried; the same attempt works once the key is fixed
    (Stripe ran nothing). Any other error is a refusal Stripe caches for the key, so it
    isn't retried and declines.
    """
    for retried in (False, True):
        try:
            return create(), None
        except stripe.CardError as error:
            on_card_error(error)
            return None, PlacementStatus.DECLINED
        except CONFIGURATION_STRIPE_ERRORS:
            logger.error(
                "Stripe refused the API key creating the card hold for user %s (attempt %s)",
                user.pk,
                attempt_id,
                exc_info=True,
            )
            return None, PlacementStatus.IN_PROGRESS
        except stripe.StripeError as error:
            # Checked before the IdempotencyError type: a concurrent request with the
            # same key is a 409 raised as another StripeError subclass.
            if getattr(error, "http_status", None) == 409:
                return None, PlacementStatus.IN_PROGRESS
            if isinstance(error, stripe.IdempotencyError):
                return None, PlacementStatus.CHANGED
            if not isinstance(error, RETRYABLE_STRIPE_ERRORS):
                # An intent Stripe made anyway is unknown to us, hence an error log.
                logger.error(
                    "Stripe refused the card hold for user %s (attempt %s)",
                    user.pk,
                    attempt_id,
                    exc_info=True,
                )
                return None, PlacementStatus.DECLINED
            log = logger.error if retried else logger.warning
            log(
                "No usable answer creating the card hold for user %s (attempt %s)%s",
                user.pk,
                attempt_id,
                " on the retry" if retried else "; retrying with the same key",
                exc_info=True,
            )
    return None, PlacementStatus.IN_PROGRESS


def _authorize(
    *,
    user: "AbstractBaseUser",
    attempt_id: uuid.UUID | str,
    stripe_customer_id: str,
    payment_method: Any,
    amount_cents: int,
    currency: str,
    metadata: dict[str, str] | None,
    card_hold_id: int | None = None,
) -> tuple[Any, PlacementStatus | None]:
    """Create the PaymentIntent (see :func:`_create_intent`). A decline abandons the
    PaymentIntent Stripe sends along with it."""

    def declined(error: stripe.CardError) -> None:
        failed = stripe_id(stripe_field(getattr(error, "error", None), "payment_intent"))
        logger.info("Card hold declined for user %s (PaymentIntent %s)", user.pk, failed)
        if failed and card_hold_id is not None:
            # On the attempt's own row, which abandoning then releases.
            _attach_send(card_hold_id, failed, {"customer": user, "attempt_id": attempt_id})
        abandon_hold(
            failed,
            user=user,
            attempt_id=attempt_id,
            stripe_customer_id=stripe_customer_id,
            payment_method=payment_method,
        )

    return _create_intent(
        lambda: create_hold_payment_intent(
            user=user,
            attempt_id=attempt_id,
            stripe_customer_id=stripe_customer_id,
            payment_method=payment_method,
            amount_cents=amount_cents,
            currency=currency,
            metadata=metadata,
            card_hold_id=card_hold_id,
        ),
        user=user,
        attempt_id=attempt_id,
        on_card_error=declined,
    )


def _save_card_for_later(
    *,
    user: "AbstractBaseUser",
    attempt_id: uuid.UUID | str,
    stripe_customer_id: str,
    payment_method: Any,
    target: Model,
    link: Callable[["AbstractCardHold"], Model] | None,
    expected_amount_cents: int | None,
    currency: str,
    metadata: dict[str, str] | None,
) -> PlacementResult:
    """The first pass of a scheduled hold: save the card with an off-session SetupIntent
    (nothing is authorized), record its ``pending`` row, and link it ``scheduled``.

    Mirrors the PaymentIntent pass: same retry rules, the same replay re-read, and
    ``requires_action`` (with the SetupIntent's client secret) when the bank wants the
    customer to authenticate; :func:`complete_setup_on_session` is the second pass.
    """

    def declined(error: stripe.CardError) -> None:
        logger.info("Saving the card declined for user %s (attempt %s)", user.pk, attempt_id)

    setup_intent, refusal = _create_intent(
        lambda: create_hold_setup_intent(
            user=user,
            attempt_id=attempt_id,
            stripe_customer_id=stripe_customer_id,
            payment_method=payment_method,
            metadata=metadata,
        ),
        user=user,
        attempt_id=attempt_id,
        on_card_error=declined,
    )
    if refusal is not None:
        return PlacementResult(refusal)
    if is_idempotent_replay(setup_intent):
        try:
            setup_intent = retrieve_setup_intent(stripe_id(setup_intent))
        except stripe.StripeError:
            logger.warning(
                "Could not re-read replayed SetupIntent %s", stripe_id(setup_intent), exc_info=True
            )
            return PlacementResult(PlacementStatus.IN_PROGRESS)
    status = stripe_field(setup_intent, "status")
    if status in TERMINAL_SETUP_STATUSES:
        return PlacementResult(PlacementStatus.DECLINED)
    record_pending_setup(
        user=user,
        attempt_id=attempt_id,
        stripe_customer_id=stripe_customer_id,
        setup_intent=setup_intent,
        payment_method=payment_method,
        currency=currency,
    )
    if status == "requires_action":
        return PlacementResult(
            PlacementStatus.REQUIRES_ACTION,
            client_secret=stripe_field(setup_intent, "client_secret"),
            intent_type="setup_intent",
        )
    if status != "succeeded":
        return PlacementResult(PlacementStatus.IN_PROGRESS)
    return _place_if_due(
        _complete(
            setup_intent=setup_intent,
            link=link,
            target=target,
            expected_amount_cents=expected_amount_cents,
        )
    )


def _place_if_due(result: PlacementResult) -> PlacementResult:
    """A hold just scheduled whose day has already come (the date moved into the window
    while the card was being saved) is placed off-session at once, while deferral is on
    (:func:`place_scheduled` checks)."""
    if result.status != PlacementStatus.SCHEDULED or result.hold is None:
        return result
    if result.hold.hold_on is not None and result.hold.hold_on > _today():
        return result
    placed = place_scheduled(result.hold.pk)
    if placed is not None and placed.status == PlacementStatus.PLACED:
        placed.target = placed.target or result.target
        return placed
    # Still to be placed, or failed: the customer sees a failed hold as scheduled.
    result.hold.refresh_from_db()
    return result


def _priced_card(
    adapter: HoldTarget,
    target: Model,
    *,
    user: "AbstractBaseUser",
    attempt_id: uuid.UUID | str,
    payment_method_id: str,
    stripe_customer_id: str,
    expected_amount_cents: int | None,
) -> tuple[Any, int, PlacementResult | None]:
    """The first pass's checks before anything is created in Stripe: the card, read from
    Stripe (:func:`usable_payment_method`), and the target's price on it. Returns
    ``(payment_method, amount_cents, None)``, or ``(None, 0, answer)`` to stop: ``in_progress`` when
    Stripe gave no usable answer, ``declined`` for an unusable card or nothing to hold,
    ``amount_changed`` when the page showed another estimate."""
    try:
        payment_method = usable_payment_method(payment_method_id, stripe_customer_id)
    except stripe.StripeError:
        logger.error(
            "No usable answer reading PaymentMethod %s for user %s (attempt %s)",
            payment_method_id,
            user.pk,
            attempt_id,
            exc_info=True,
        )
        return None, 0, PlacementResult(PlacementStatus.IN_PROGRESS)
    if payment_method is None:
        return None, 0, PlacementResult(PlacementStatus.DECLINED)
    estimated, _buffer, amount = price(adapter, target, card_of(payment_method))
    if expected_amount_cents is not None and estimated != expected_amount_cents:
        return None, 0, PlacementResult(PlacementStatus.AMOUNT_CHANGED)
    if (amount if adapter.uses_holds else estimated) <= 0:
        logger.warning("Nothing to hold for user %s (attempt %s)", user.pk, attempt_id)
        return None, 0, PlacementResult(PlacementStatus.DECLINED)
    return payment_method, amount, None


def _send_on_session(
    *,
    user: "AbstractBaseUser",
    attempt_id: uuid.UUID | str,
    stripe_customer_id: str,
    payment_method: Any,
    amount_cents: int,
    currency: str,
    metadata: dict[str, str] | None,
) -> tuple[Any, PlacementStatus | None]:
    """The first pass's PaymentIntent, read live: ``(payment_intent, None)`` or
    ``(None, answer)``.

    The attempt's row is written before the create (:func:`_begin_send`). A row that
    already carries its PaymentIntent (a webhook recorded it, or an earlier pass) is
    read, not created again: Stripe could answer the create with a 5xx it saved for the
    key. A create unanswered for :data:`PLACEMENT_KEY_TTL` is never replayed: it answers
    ``in_progress`` until the sweep reconciles it and closes the attempt. A decline
    closes the row; a replayed answer is re-read, as it may describe a PaymentIntent
    cancelled since.
    """
    sending = _begin_send(
        user=user,
        attempt_id=attempt_id,
        stripe_customer_id=stripe_customer_id,
        payment_method=payment_method,
        amount_cents=amount_cents,
        currency=currency,
    )
    if sending is None:
        return None, PlacementStatus.IN_PROGRESS
    replayed_id = sending.stripe_payment_intent_id
    if replayed_id is not None and (
        sending.amount_cents != amount_cents
        or sending.stripe_payment_method_id != stripe_id(payment_method)
    ):
        # What Stripe answers a key resent with other parameters.
        return None, PlacementStatus.CHANGED
    if replayed_id is None:
        if _send_is_stale(sending):
            logger.warning(
                "Card hold %s: its create got no usable answer for %s; reconciling, not"
                " replaying it",
                sending.pk,
                PLACEMENT_KEY_TTL,
            )
            return None, PlacementStatus.IN_PROGRESS
        payment_intent, refusal = _authorize(
            user=user,
            attempt_id=attempt_id,
            stripe_customer_id=stripe_customer_id,
            payment_method=payment_method,
            amount_cents=amount_cents,
            currency=currency,
            metadata=metadata,
            card_hold_id=sending.pk,
        )
        if refusal == PlacementStatus.DECLINED:
            _close_send(sending.pk)
        if refusal is not None or not is_idempotent_replay(payment_intent):
            return payment_intent, refusal
        replayed_id = stripe_id(payment_intent)
    try:
        return retrieve_payment_intent(replayed_id), None
    except stripe.StripeError:
        logger.warning("Could not re-read replayed PaymentIntent %s", replayed_id, exc_info=True)
        return None, PlacementStatus.IN_PROGRESS


def authorize_on_session(
    *,
    user: "AbstractBaseUser",
    attempt_id: uuid.UUID | str,
    payment_method_id: str,
    stripe_customer_id: str,
    target: Model,
    link: Callable[["AbstractCardHold"], Model] | None = None,
    expected_amount_cents: int | None = None,
    currency: str = "usd",
    metadata: dict[str, str] | None = None,
) -> PlacementResult:
    """The first pass: authorize a hold for ``target`` while the customer is present.

    A target charged now (no date after today, :func:`charged_later`) answers
    ``charge_now`` before Stripe is called: no hold is needed, and the project charges
    it directly. A target whose adapter doesn't use holds (``uses_holds = False``) has
    its card saved with an off-session SetupIntent and is linked ``saved`` (answering
    ``card_saved``): nothing is authorized, and :func:`capture` charges it on the date.

    ``target`` is priced through its adapter before Stripe is called. It may be unsaved
    (the project validates its input into an instance, and ``link`` saves it); pass a
    saved one, and no ``link``, to hold an existing target, which is then locked first;
    if its previous hold was ``released``, that row is re-armed (:func:`_rearm`), and any
    other previous hold refuses. A released hold whose cancel Stripe hasn't confirmed is
    cancelled (and confirmed) first; until Stripe confirms it, ``in_progress``.
    ``expected_amount_cents`` is the estimate the page showed: a mismatch places
    nothing. Raises :class:`CardHoldInTransaction` inside a transaction.

    With ``CARD_HOLDS_DEFERRAL_ENABLED``, a target dated further out than the window
    authorizes nothing: the card is saved with an off-session SetupIntent and the hold is
    linked ``scheduled``, answering ``scheduled`` with ``hold_on`` (or
    ``requires_action`` for the SetupIntent, whose second pass is
    :func:`complete_setup_on_session`).
    """
    _ensure_outside_transaction()
    found = find_attempt(user, attempt_id)
    if found is not None:
        return found
    if not utils.stripe_configured() or not stripe_customer_id:
        return PlacementResult(PlacementStatus.DECLINED)
    adapter = target_for_model(type(target))
    if not charged_later(adapter, target):
        return PlacementResult(PlacementStatus.CHARGE_NOW, target=target)
    refusal = _may_hold(target)
    if refusal is not None:
        # Checked again under the locks; refusing here just spares a PaymentIntent.
        return PlacementResult(refusal)

    payment_method, amount, stop = _priced_card(
        adapter,
        target,
        user=user,
        attempt_id=attempt_id,
        payment_method_id=payment_method_id,
        stripe_customer_id=stripe_customer_id,
        expected_amount_cents=expected_amount_cents,
    )
    if stop is not None:
        return stop

    if not adapter.uses_holds or deferred_hold_on(adapter, target) is not None:
        return _save_card_for_later(
            user=user,
            attempt_id=attempt_id,
            stripe_customer_id=stripe_customer_id,
            payment_method=payment_method,
            target=target,
            link=link,
            expected_amount_cents=expected_amount_cents,
            currency=currency,
            metadata=metadata,
        )

    payment_intent, refusal = _send_on_session(
        user=user,
        attempt_id=attempt_id,
        stripe_customer_id=stripe_customer_id,
        payment_method=payment_method,
        amount_cents=amount,
        currency=currency,
        metadata=metadata,
    )
    if refusal is not None:
        return PlacementResult(refusal)

    abandon = {
        "user": user,
        "attempt_id": attempt_id,
        "stripe_customer_id": stripe_customer_id,
        "payment_intent": payment_intent,
        "payment_method": payment_method,
    }
    try:
        record_pending_hold(
            user=user,
            attempt_id=attempt_id,
            stripe_customer_id=stripe_customer_id,
            payment_intent=payment_intent,
            payment_method=payment_method,
        )
    except Exception:
        # An authorization with no hold row could never be released by the sweep.
        abandon_hold(stripe_id(payment_intent), **abandon)
        raise

    status = stripe_field(payment_intent, "status")
    if status == "requires_action":
        return PlacementResult(
            PlacementStatus.REQUIRES_ACTION,
            client_secret=stripe_field(payment_intent, "client_secret"),
            intent_type="payment_intent",
        )
    if status == "requires_capture":
        return _complete(
            payment_intent=payment_intent,
            link=link,
            target=target,
            expected_amount_cents=expected_amount_cents,
        )
    abandon_hold(stripe_id(payment_intent), **abandon)
    return PlacementResult(PlacementStatus.DECLINED)


def complete_on_session(
    payment_intent_id: str,
    link: Callable[["AbstractCardHold"], Model] | None = None,
    *,
    user: "AbstractBaseUser",
    attempt_id: uuid.UUID | str,
    stripe_customer_id: str,
    target: Model | None = None,
    expected_amount_cents: int | None = None,
) -> PlacementResult:
    """The second pass, after the customer authenticated: link the PaymentIntent.

    A PaymentIntent that isn't this user's attempt is refused without being touched.
    The card is always the PaymentIntent's own. A PaymentIntent still waiting on the
    customer or on Stripe (``requires_action``, ``requires_confirmation``,
    ``processing``) answers ``in_progress`` and is left alone; only a finished one
    (``canceled``, ``requires_payment_method``) is abandoned. Under the hold's lock, a
    hold already linked returns its target; otherwise ``link`` places the target (or
    ``target``, an existing one, is used). Raises :class:`CardHoldInTransaction` inside
    a transaction.
    """
    _ensure_outside_transaction()
    found = find_attempt(user, attempt_id)
    if found is not None:
        return found
    if not utils.stripe_configured() or not stripe_customer_id:
        return PlacementResult(PlacementStatus.DECLINED)
    try:
        payment_intent = retrieve_payment_intent(payment_intent_id)
    except stripe.StripeError:
        logger.warning("Could not retrieve PaymentIntent %s", payment_intent_id, exc_info=True)
        return PlacementResult(PlacementStatus.DECLINED)

    metadata = stripe_field(payment_intent, "metadata") or {}
    if (
        stripe_id(stripe_field(payment_intent, "customer")) != stripe_customer_id
        or str(stripe_field(metadata, "user_id")) != str(user.pk)
        or str(stripe_field(metadata, "attempt_id")) != str(attempt_id)
    ):
        logger.warning(
            "PaymentIntent %s refused on the second pass: not user %s's attempt",
            payment_intent_id,
            user.pk,
        )
        return PlacementResult(PlacementStatus.DECLINED)

    status = stripe_field(payment_intent, "status")
    if status in TERMINAL_INTENT_STATUSES:
        abandon_hold(
            stripe_id(payment_intent),
            user=user,
            attempt_id=attempt_id,
            stripe_customer_id=stripe_customer_id,
            payment_intent=payment_intent,
        )
        return PlacementResult(PlacementStatus.DECLINED)
    if status != "requires_capture":
        return PlacementResult(PlacementStatus.IN_PROGRESS)
    try:
        record_pending_hold(
            user=user,
            attempt_id=attempt_id,
            stripe_customer_id=stripe_customer_id,
            payment_intent=payment_intent,
        )
    except Exception:
        # As on the first pass: an authorization with no hold row could never be released.
        abandon_hold(
            stripe_id(payment_intent),
            user=user,
            attempt_id=attempt_id,
            stripe_customer_id=stripe_customer_id,
            payment_intent=payment_intent,
        )
        raise
    return _complete(
        payment_intent=payment_intent,
        link=link,
        target=target,
        expected_amount_cents=expected_amount_cents,
    )


def complete_setup_on_session(
    setup_intent_id: str,
    link: Callable[["AbstractCardHold"], Model] | None = None,
    *,
    user: "AbstractBaseUser",
    attempt_id: uuid.UUID | str,
    stripe_customer_id: str,
    target: Model | None = None,
    expected_amount_cents: int | None = None,
) -> PlacementResult:
    """The second pass of a scheduled hold, after the customer authenticated the
    SetupIntent that saves their card: link it ``scheduled``.

    The same rules as :func:`complete_on_session`: the attempt answers first, a
    SetupIntent that isn't this user's attempt is refused untouched, one still waiting
    (``requires_action``, ``processing``) answers ``in_progress``, and a finished one that
    saved nothing (``canceled``, ``requires_payment_method``) declines. A hold whose day
    has already come is placed off-session at once. Raises :class:`CardHoldInTransaction`
    inside a transaction.
    """
    _ensure_outside_transaction()
    found = find_attempt(user, attempt_id)
    if found is not None:
        return found
    if not utils.stripe_configured() or not stripe_customer_id:
        return PlacementResult(PlacementStatus.DECLINED)
    try:
        setup_intent = retrieve_setup_intent(setup_intent_id)
    except stripe.StripeError:
        logger.warning("Could not retrieve SetupIntent %s", setup_intent_id, exc_info=True)
        return PlacementResult(PlacementStatus.DECLINED)

    metadata = stripe_field(setup_intent, "metadata") or {}
    if (
        stripe_id(stripe_field(setup_intent, "customer")) != stripe_customer_id
        or str(stripe_field(metadata, "user_id")) != str(user.pk)
        or str(stripe_field(metadata, "attempt_id")) != str(attempt_id)
    ):
        logger.warning(
            "SetupIntent %s refused on the second pass: not user %s's attempt",
            setup_intent_id,
            user.pk,
        )
        return PlacementResult(PlacementStatus.DECLINED)

    status = stripe_field(setup_intent, "status")
    if status in TERMINAL_SETUP_STATUSES:
        abandon_setup(stripe_id(setup_intent))
        return PlacementResult(PlacementStatus.DECLINED)
    if status != "succeeded":
        return PlacementResult(PlacementStatus.IN_PROGRESS)
    record_pending_setup(
        user=user,
        attempt_id=attempt_id,
        stripe_customer_id=stripe_customer_id,
        setup_intent=setup_intent,
    )
    return _place_if_due(
        _complete(
            setup_intent=setup_intent,
            link=link,
            target=target,
            expected_amount_cents=expected_amount_cents,
        )
    )


def _lock_hold_of_payment_intent(payment_intent_id: str) -> "AbstractCardHold | None":
    """``SELECT ... FOR UPDATE`` the hold that carries ``payment_intent_id``.

    Looked up at most twice, deliberately. Under READ COMMITTED, a ``FOR UPDATE`` that
    waited on a row the lock holder then deleted returns nothing, even when that same
    transaction moved the PaymentIntent to another row: a re-arm folds the pending row
    into the target's existing hold. A second statement takes a fresh snapshot and finds
    where it went. Two lookups suffice: a PaymentIntent only ever moves once.
    """
    return _lock_hold_of_intent(stripe_payment_intent_id=payment_intent_id)


def _lock_hold_of_intent(**intent: str) -> "AbstractCardHold | None":
    """:func:`_lock_hold_of_payment_intent` for either intent column."""
    CardHold = _holds()
    for _lookup in ("first", "after a concurrent re-arm"):
        hold = CardHold.objects.select_for_update().filter(**intent).first()
        if hold is not None:
            return hold
    return None


def _complete(
    *,
    link: Callable[["AbstractCardHold"], Model] | None,
    target: Model | None,
    expected_amount_cents: int | None,
    payment_intent: Any = None,
    setup_intent: Any = None,
) -> PlacementResult:
    """Under the locks (target first, then hold), link the hold to its target.

    No Stripe call runs inside. A hold already linked returns its target and is never
    cancelled; a refusal releases the still-unlinked hold and cancels its PaymentIntent
    once the block commits; an exception rolls back, abandons the hold and is re-raised.
    With ``setup_intent`` (a card saved for later) the hold is linked ``scheduled``;
    nothing is held, so a refusal has nothing to cancel in Stripe.
    """
    CardHold = _holds()
    intent = payment_intent if payment_intent is not None else setup_intent
    payment_intent_id = stripe_id(payment_intent) if payment_intent is not None else None
    setup_intent_id = stripe_id(setup_intent) if setup_intent is not None else None
    card = card_of(stripe_field(intent, "payment_method"))
    existing = target if target is not None and target.pk is not None else None
    result = PlacementResult(PlacementStatus.DECLINED)
    try:
        with transaction.atomic():
            locked = None
            if existing is not None:
                locked = target_for_model(type(existing)).lock(existing.pk)
            if payment_intent_id is not None:
                hold = _lock_hold_of_payment_intent(payment_intent_id)
            else:
                hold = _lock_hold_of_intent(stripe_setup_intent_id=setup_intent_id)
            if hold is None:
                return result
            if hold.target_document_id is not None:
                # Placed by a concurrent call for the same intent.
                return PlacementResult(_placed_status(hold), target=hold.target, hold=hold)

            if hold.status == CardHold.Status.PENDING:
                try:
                    with transaction.atomic():
                        return _link(
                            hold,
                            payment_intent=payment_intent,
                            scheduling=setup_intent is not None,
                            card=card,
                            linked=link(hold) if link is not None else (locked or existing),
                            expected_amount_cents=expected_amount_cents,
                            locked_target=locked,
                        )
                except _RearmPending:
                    # Rolled back to the savepoint; the pending row stays, so a retry of
                    # the attempt (the same key) carries on once Stripe confirms the
                    # cancel, and the sweep releases it if nobody retries.
                    return PlacementResult(PlacementStatus.IN_PROGRESS)
                except HoldRefused as refused:
                    result = PlacementResult(PlacementStatus.REFUSED, errors=refused.errors)
                except _AmountChanged:
                    result = PlacementResult(PlacementStatus.AMOUNT_CHANGED)
                hold.status = CardHold.Status.RELEASED
                hold.release_reason = CardHold.ReleaseReason.ABANDONED
                hold.save(update_fields=["status", "release_reason", "modified"])
                send_on_commit(card_hold_released, hold_id=hold.pk)
            # Released or being released (an earlier refusal, the sweep): a replayed
            # Stripe response must not place a target on it. Unlinked under the lock, so
            # releasing it can't cancel a placed target.
            if payment_intent_id is not None:
                release_on_commit(hold.pk, claimed=True, payment_intent_id=payment_intent_id)
            elif hold.release_confirmed_at is None:
                # A saved card holds nothing: the release is confirmed as it is written.
                CardHold.objects.filter(pk=hold.pk, status=CardHold.Status.RELEASED).update(
                    release_confirmed_at=timezone.now()
                )
    except Exception:
        if payment_intent_id is not None:
            abandon_hold(payment_intent_id)
        else:
            abandon_setup(setup_intent_id)
        raise
    return result


def _is_same_object(first: Model | None, second: Model | None) -> bool:
    return (
        first is not None
        and second is not None
        and first._meta.concrete_model is second._meta.concrete_model
        and first.pk == second.pk
    )


def _link(
    hold: "AbstractCardHold",
    *,
    payment_intent: Any,
    card: Card,
    linked: Model | None,
    expected_amount_cents: int | None,
    locked_target: Model | None = None,
    scheduling: bool = False,
) -> PlacementResult:
    """Re-check and re-price ``linked``, and attach the hold; raises to refuse (rolled back).

    The target must be the customer's and still able to take a hold (:func:`_holdable`).
    A target that already has a hold keeps that one row (one hold per target): a
    ``released`` one is re-armed with this authorization (:func:`_rearm`), but only when
    ``linked`` is the very object locked before the holds (``locked_target``, the
    existing target passed to placement) and the hold wasn't released to be charged
    afresh (:func:`_rearmable`). Any other previous hold refuses.

    ``scheduling`` (a card saved for later): nothing was authorized, so only the estimate
    is compared, and the hold is linked ``scheduled`` with ``hold_on`` read under the
    lock (today, when the date moved into the window meanwhile); or ``saved``, with no
    ``hold_on``, when the target's adapter doesn't use holds.

    A previous hold released but not confirmed cancelled in Stripe raises
    :class:`_RearmPending`. Another placement linking the same target first (its
    ``link`` returned an existing target it didn't lock) refuses.
    """
    if linked is None or linked.pk is None:
        raise HoldRefused()
    adapter = target_for_model(type(linked))
    owner = adapter.owner(linked)
    if owner is None or owner.pk != hold.customer_id:
        logger.warning("Card hold %s refused: its target isn't the customer's", hold.pk)
        raise HoldRefused()
    if not _holdable(adapter, linked):
        logger.warning("Card hold %s refused: its target can't take a hold now", hold.pk)
        raise HoldRefused()
    estimated, buffer, amount = price(adapter, linked, card)
    if (expected_amount_cents is not None and estimated != expected_amount_cents) or (
        not scheduling and amount != stripe_field(payment_intent, "amount")
    ):
        raise _AmountChanged()
    Status = type(hold).Status
    saving = scheduling and not adapter.uses_holds
    hold_on = hold_on_for(adapter, linked) if scheduling and not saving else None
    document = DocumentId.get_or_create_for_object(linked)
    previous = (
        type(hold)
        .objects.select_for_update()
        .filter(target_document=document)
        .exclude(pk=hold.pk)
        .first()
    )
    if previous is not None:
        if not _rearmable(previous) or not _is_same_object(linked, locked_target):
            logger.warning(
                "Card hold %s refused: its target already has hold %s (%s)",
                hold.pk,
                previous.pk,
                previous.status,
            )
            raise HoldRefused()
        if _release_unconfirmed(previous):
            logger.info(
                "Card hold %s: hold %s's cancel isn't confirmed yet; not re-armed",
                hold.pk,
                previous.pk,
            )
            raise _RearmPending()
        return _rearm(
            previous,
            hold,
            payment_intent=None if scheduling else payment_intent,
            linked=linked,
            estimated=estimated,
            buffer=buffer,
            amount=amount,
            hold_on=hold_on,
            status=Status.SAVED if saving else None,
        )

    hold.target_document = document
    hold.estimated_amount_cents = estimated
    hold.buffer_percent = buffer
    hold.amount_cents = amount
    if scheduling:
        hold.status = Status.SAVED if saving else Status.SCHEDULED
        hold.hold_on = hold_on
        _save_linked(hold)
        return PlacementResult(_placed_status(hold), target=linked, hold=hold)
    hold.status = Status.AUTHORIZED
    hold.expires_at = hold_expiry(payment_intent)
    _save_linked(hold)
    send_on_commit(card_hold_authorized, hold=hold, target=linked)
    return PlacementResult(PlacementStatus.PLACED, target=linked, hold=hold)


def _save_linked(hold: "AbstractCardHold") -> None:
    """Save a hold just linked to its target. A concurrent placement that linked another
    hold to the same target first (a ``link`` returning an existing target without
    locking it) trips the one-to-one: refused, not raised."""
    try:
        with transaction.atomic():
            hold.save()
    except IntegrityError:
        logger.warning("Card hold %s refused: its target got another hold meanwhile", hold.pk)
        raise HoldRefused() from None


def _holdable(adapter: HoldTarget, target: Model) -> bool:
    """Whether a saved target can take a hold: not cancelled, not done with the card, and
    among the adapter's ``filter_holdable`` targets."""
    one = adapter.model._default_manager.filter(pk=target.pk)
    return (
        not is_cancelled(adapter, target.pk)
        and not is_card_released(adapter, target.pk)
        and adapter.filter_holdable(one).exists()
    )


def _rearmable(hold: "AbstractCardHold") -> bool:
    """A ``released`` hold that may take a new authorization: not one released so the
    amount could be charged afresh (``for_charge``), nor one charged instead, nor a
    failed deferred hold staff cancelled (``failed_at``: a failure is final), nor one
    released only to be scheduled again (``rescheduled``, ``not_holdable``:
    :func:`reschedule_hold` owns it).

    One whose cancel Stripe hasn't confirmed yet is rearmable, but not yet
    (:func:`_release_unconfirmed`): re-arming it would drop the only record of an
    authorization that may still be live."""
    return (
        hold.status == hold.Status.RELEASED
        and hold.release_reason
        not in (hold.ReleaseReason.FOR_CHARGE, *hold.BACK_TO_SCHEDULED_REASONS)
        and not hold.charge_key
        and hold.charged_at is None
        and hold.failed_at is None
    )


def _release_unconfirmed(hold: "AbstractCardHold") -> bool:
    """A released hold whose PaymentIntent Stripe hasn't confirmed cancelled."""
    return bool(hold.stripe_payment_intent_id) and hold.release_confirmed_at is None


def _may_hold(target: Model) -> PlacementStatus | None:
    """The early, lock-free version of the checks :func:`_link` repeats under the locks;
    ``None`` when the target may take a hold, else the answer. An unsaved target may; a
    saved one must be :func:`_holdable` and have no hold, or only a :func:`_rearmable`
    one (``refused`` otherwise).

    A rearmable hold whose cancel Stripe hasn't confirmed is released now (Stripe is
    asked; no lock is held): ``in_progress`` until Stripe confirms it.
    """
    if target.pk is None:
        return None
    if not _holdable(target_for_model(type(target)), target):
        return PlacementStatus.REFUSED
    previous = _holds().objects.for_target(target).first()
    if previous is None:
        return None
    if not _rearmable(previous):
        return PlacementStatus.REFUSED
    if _release_unconfirmed(previous) and not _confirm_release(previous):
        return PlacementStatus.IN_PROGRESS
    return None


def _confirm_release(hold: "AbstractCardHold") -> bool:
    """Ask Stripe to cancel a released hold's PaymentIntent now, so it can be re-armed;
    whether Stripe confirmed it. Any Stripe error is logged and answers ``False``."""
    try:
        release(hold.pk, claimed=True, payment_intent_id=hold.stripe_payment_intent_id)
    except stripe.StripeError:
        logger.warning("Could not confirm the release of card hold %s", hold.pk, exc_info=True)
        return False
    return (
        _holds()
        .objects.filter(
            pk=hold.pk,
            stripe_payment_intent_id=hold.stripe_payment_intent_id,
            release_confirmed_at__isnull=False,
        )
        .exists()
    )


# Copied from the new pending row onto the re-armed one.
_REARM_COPIED_FIELDS = (
    "customer_id",
    "stripe_customer_id",
    "attempt_id",
    "stripe_payment_method_id",
    "card_brand",
    "card_last4",
    "card_exp_month",
    "card_exp_year",
    "card_funding",
    "card_fingerprint",
    "currency",
)


def _rearm(
    previous: "AbstractCardHold",
    pending: "AbstractCardHold",
    *,
    payment_intent: Any,
    linked: Model,
    estimated: int,
    buffer: Decimal,
    amount: int,
    hold_on: datetime.date | None = None,
    status: str | None = None,
) -> PlacementResult:
    """Re-arm a target's ``released`` hold with a new authorization, on the same row.

    Runs under the target's lock, then the pending hold's, then ``previous``'s. The new
    authorization's pending row is folded into ``previous`` and deleted (its PaymentIntent
    id moves over; ids stay unique). The replaced PaymentIntent and attempt ids are
    appended to ``previous_payment_intent_ids`` / ``previous_attempt_ids``, so the old
    attempt still finds its target. The placement fields are reset: card, amounts,
    expiry, status, attempt, and the failure, release and deferred-placement claim
    fields.

    Only ``released`` holds are re-armed, and not one released to be charged afresh
    (:func:`_rearmable`). An open hold (``pending``, ``authorized``) or a ``captured`` one
    refuses, and so do ``failed`` and ``scheduled``: a failed hold is final, and neither
    the sweep nor a change of date may re-arm it.

    With no ``payment_intent`` (a card saved for later), the row is re-armed
    ``scheduled`` for ``hold_on`` (or ``status``: ``saved``, for an adapter that doesn't
    use holds): no PaymentIntent, no expiry, the new SetupIntent. The charge block of
    the old authorization (a declined capture) goes with it.
    """
    payment_history = list(previous.previous_payment_intent_ids or [])
    if previous.stripe_payment_intent_id:
        payment_history.append(previous.stripe_payment_intent_id)
    attempt_history = list(previous.previous_attempt_ids or [])
    if previous.attempt_id:
        attempt_history.append(str(previous.attempt_id))
    for field in _REARM_COPIED_FIELDS:
        setattr(previous, field, getattr(pending, field))
    new_payment_intent_id = pending.stripe_payment_intent_id
    new_setup_intent_id = pending.stripe_setup_intent_id
    pending.delete()  # frees its intent ids before the re-armed row takes them

    scheduling = payment_intent is None
    Status = type(previous).Status
    previous.stripe_payment_intent_id = new_payment_intent_id
    previous.stripe_setup_intent_id = new_setup_intent_id
    previous.previous_payment_intent_ids = payment_history
    previous.previous_attempt_ids = attempt_history
    previous.status = status or (Status.SCHEDULED if scheduling else Status.AUTHORIZED)
    previous.estimated_amount_cents = estimated
    previous.buffer_percent = buffer
    previous.amount_cents = amount
    previous.expires_at = None if scheduling else hold_expiry(payment_intent)
    previous.hold_on = hold_on if scheduling else None
    previous.failed_at = None
    previous.failure_code = ""
    previous.placement_key = ""
    previous.placement_amount_cents = None
    previous.placement_claimed_at = None
    previous.placement_sent_at = None
    previous.release_confirmed_at = None
    previous.release_requested_at = None
    previous.release_reason = ""
    previous.kept_at = None
    previous.kept_by = None
    previous.charge_blocked_reason = ""
    # The old authorization's capture: the new one hasn't been asked to capture anything.
    previous.capture_sent_at = None
    previous.requested_amount_cents = None
    previous.difference_amount_cents = None
    previous.save()
    logger.info(
        "Card hold %s re-armed with %s (was %s)",
        previous.pk,
        new_payment_intent_id or new_setup_intent_id,
        payment_history[-1] if payment_history else None,
    )
    if scheduling:
        return PlacementResult(_placed_status(previous), target=linked, hold=previous)
    send_on_commit(card_hold_authorized, hold=previous, target=linked)
    return PlacementResult(PlacementStatus.PLACED, target=linked, hold=previous)


# --- State changes --------------------------------------------------------------------


def _set_released(
    card_hold_id: int, reason: str = "", *, charge_key: str = "", **filters: Any
) -> bool:
    """Mark the hold ``released`` (for ``reason``) if it is still open (and matches
    ``filters``); whether this call changed it. ``charge_key`` claims the charge that
    follows in the same statement (see :func:`_charge_once`)."""
    CardHold = _holds()
    changes: dict[str, Any] = {
        "status": CardHold.Status.RELEASED,
        "release_reason": reason,
        "modified": timezone.now(),
    }
    if charge_key:
        changes.update(charge_key=charge_key, charge_claimed_at=changes["modified"])
    changed = bool(
        CardHold.objects.filter(
            pk=card_hold_id, status__in=CardHold.OPEN_STATUSES, **filters
        ).update(**changes)
    )
    if changed:
        send_on_commit(card_hold_released, hold_id=card_hold_id)
    return changed


def _release_scheduled(card_hold_id: int, reason: str, *, charge_key: str = "") -> bool:
    """Mark a ``scheduled`` (or ``saved``) hold ``released`` (and confirmed: nothing is
    held in Stripe), unless its placement is under way (``placement_key``, an off-session
    create whose outcome isn't settled yet). Whether this call changed it. No Stripe
    call. ``charge_key`` claims the charge that follows in the same statement."""
    CardHold = _holds()
    now = timezone.now()
    changes: dict[str, Any] = {
        "status": CardHold.Status.RELEASED,
        "release_reason": reason,
        "release_confirmed_at": now,
        "modified": now,
    }
    if charge_key:
        changes.update(charge_key=charge_key, charge_claimed_at=now)
    changed = bool(
        CardHold.objects.filter(
            pk=card_hold_id,
            status__in=CardHold.UNPLACED_STATUSES,
            placement_key="",
            charge_key="",
        ).update(**changes)
    )
    if changed:
        send_on_commit(card_hold_released, hold_id=card_hold_id)
    return changed


def _scoped(payment_intent_id: str | None) -> dict[str, Any]:
    return {"stripe_payment_intent_id": payment_intent_id} if payment_intent_id else {}


def mark_released(
    card_hold_id: int,
    payment_intent_id: str | None = None,
    *,
    confirmed: bool = False,
    reason: str = "",
    charge_key: str = "",
) -> bool:
    """Mark the hold ``released`` if it is still open (and, given ``payment_intent_id``,
    still on that authorization); whether this call changed its status.

    ``confirmed``: Stripe confirmed the cancel (or the authorization lapsed), so the
    sweep stops re-driving it; also applied to a hold already ``released``. ``reason``
    (a ``ReleaseReason``) is recorded only with the change of status: a hold released
    ``for_charge`` is never re-armed.
    """
    changed = _set_released(
        card_hold_id, reason, charge_key=charge_key, **_scoped(payment_intent_id)
    )
    if confirmed:
        CardHold = _holds()
        CardHold.objects.filter(
            pk=card_hold_id,
            status=CardHold.Status.RELEASED,
            release_confirmed_at__isnull=True,
            **_scoped(payment_intent_id),
        ).update(release_confirmed_at=timezone.now(), release_requested_at=None)
    return changed


def claim_orphan(card_hold_id: int) -> bool:
    """Atomically mark an unlinked hold released, if it still is one.

    Fails when the hold was linked or closed meanwhile, so a sweep racing a late second
    pass never cancels a placed target's hold.
    """
    return _set_released(
        card_hold_id, _holds().ReleaseReason.ABANDONED, target_document__isnull=True
    )


def mark_captured(
    card_hold_id: int,
    *,
    amount_cents: int | None = None,
    payment_intent_id: str | None = None,
) -> bool:
    """Mark the hold ``captured``, whatever its status: Stripe says it happened. Records
    the amount captured and when. Whether this call changed it.

    The target is then ``paid`` when the amount captured is the one the last
    :func:`capture` asked for (``requested_amount_cents``); it stays ``unpaid`` while the
    difference planned above it (``difference_amount_cents``) is still due, and is paid
    once that is charged too. Any other amount (a capture sent for one amount, answered
    after a later call asked for another) stays ``unpaid`` and is logged as an error, for
    someone to settle by hand. With no amount asked for on record, it is ``paid`` unless
    a difference is planned; with one asked for, it waits for the amount captured.

    A hold recorded ``captured`` without its amount (Stripe couldn't be read) gets it
    filled in by the first call that knows it, then is evaluated as above."""
    CardHold = _holds()
    scoped = _scoped(payment_intent_id)
    changed = bool(
        CardHold.objects.filter(pk=card_hold_id, **scoped)
        .exclude(status=CardHold.Status.CAPTURED)
        .update(
            status=CardHold.Status.CAPTURED,
            captured_amount_cents=amount_cents,
            captured_at=timezone.now(),
            release_requested_at=None,
            modified=timezone.now(),
        )
    )
    if not changed and amount_cents is not None:
        changed = bool(
            CardHold.objects.filter(
                pk=card_hold_id,
                status=CardHold.Status.CAPTURED,
                captured_amount_cents__isnull=True,
                **scoped,
            ).update(captured_amount_cents=amount_cents, modified=timezone.now())
        )
    row = (
        CardHold.objects.filter(pk=card_hold_id, status=CardHold.Status.CAPTURED, **scoped)
        .values_list("captured_amount_cents", "requested_amount_cents", "difference_amount_cents")
        .first()
    )
    if row is None:
        return changed
    captured, requested, planned = row
    if requested is None:
        if planned is None:
            _set_payment_status(
                card_hold_id,
                CardHold.PaymentStatus.PAID,
                (CardHold.PaymentStatus.UNPAID,),
                q=Q(
                    difference_amount_cents__isnull=True,
                    requested_amount_cents__isnull=True,
                    **scoped,
                ),
            )
        return changed
    if captured is None:
        # An amount was asked for: never ``paid`` before the amount taken is known (the
        # sweep reads it from Stripe, see ``record_card_hold_capture``).
        return changed
    if planned is not None and captured + planned == requested:
        return changed  # paid once the difference is charged
    if captured == requested:
        # Captured for what was asked: a difference an earlier call planned isn't due.
        _set_payment_status(
            card_hold_id,
            CardHold.PaymentStatus.PAID,
            (CardHold.PaymentStatus.UNPAID,),
            q=Q(captured_amount_cents=captured, requested_amount_cents=requested, **scoped),
            difference_amount_cents=None,
        )
        return changed
    logger.error(
        "Card hold %s was captured for %s, but the last capture() asked for %s (%s planned on"
        " top); not marked paid. Check Stripe and settle it by hand.",
        card_hold_id,
        captured,
        requested,
        planned,
    )
    return changed


def _set_payment_status(
    card_hold_id: int,
    payment_status: str,
    previous: tuple[str, ...],
    *,
    q: Q | None = None,
    **changes: Any,
) -> bool:
    """Move the hold's ``payment_status`` to ``payment_status`` from one of ``previous``
    (and matching ``q``), writing ``changes`` in the same conditional UPDATE; whether it
    changed. Each change sends ``payment_status_changed`` once, after the commit."""
    CardHold = _holds()
    rows = CardHold.objects.filter(pk=card_hold_id)
    if q is not None:
        rows = rows.filter(q)
    for before in previous:
        if rows.filter(payment_status=before).update(
            payment_status=payment_status, modified=timezone.now(), **changes
        ):
            hold = CardHold.objects.select_related("target_document").get(pk=card_hold_id)
            send_on_commit(
                payment_status_changed,
                hold=hold,
                target=hold.target,
                previous=before,
                payment_status=payment_status,
            )
            return True
    return False


def mark_release_in_flight(card_hold_id: int) -> None:
    """Stamp that a release task is working on the hold (the sweep skips it a while)."""
    _holds().objects.filter(pk=card_hold_id).update(release_requested_at=timezone.now())


def clear_release_in_flight(card_hold_id: int) -> None:
    """The release task is done with the hold, whatever happened: the sweep may retry."""
    _holds().objects.filter(pk=card_hold_id).update(release_requested_at=None)


def _expired(hold: "AbstractCardHold") -> bool:
    return hold.expires_at is not None and hold.expires_at <= timezone.now()


def _amount_received(payment_intent: Any) -> int | None:
    received = stripe_field(payment_intent, "amount_received")
    return received or stripe_field(payment_intent, "amount")


def _record_capture_from_stripe(card_hold_id: int, payment_intent_id: str) -> Any:
    """Stripe says the PaymentIntent was captured: mark the hold captured, with the
    amount Stripe received when it can be read. Returns the PaymentIntent, or ``None``."""
    try:
        intent = retrieve_payment_intent(payment_intent_id)
    except stripe.StripeError:
        logger.warning("Could not read captured PaymentIntent %s", payment_intent_id)
        intent = None
    mark_captured(
        card_hold_id,
        amount_cents=_amount_received(intent) if intent is not None else None,
        payment_intent_id=payment_intent_id,
    )
    logger.warning(
        "Card hold %s: PaymentIntent %s was captured, not released",
        card_hold_id,
        payment_intent_id,
    )
    return intent


def record_captured_amount(card_hold_id: int) -> bool:
    """Fill in the amount of a hold recorded ``captured`` without it (Stripe couldn't be
    read then): read its PaymentIntent, with no lock held, and record what Stripe
    received (:func:`mark_captured`, which then settles ``payment_status``). Queued by
    the sweep. Whether it was filled in; Stripe's errors propagate."""
    CardHold = _holds()
    payment_intent_id = (
        CardHold.objects.filter(
            pk=card_hold_id,
            status=CardHold.Status.CAPTURED,
            captured_amount_cents__isnull=True,
            stripe_payment_intent_id__isnull=False,
        )
        .values_list("stripe_payment_intent_id", flat=True)
        .first()
    )
    if payment_intent_id is None:
        return False
    intent = retrieve_payment_intent(payment_intent_id)
    amount = _amount_received(intent)
    if stripe_field(intent, "status") != "succeeded" or amount is None:
        logger.error(
            "Card hold %s is recorded captured, but Stripe says PaymentIntent %s is %s;"
            " its amount isn't filled in. Check Stripe.",
            card_hold_id,
            payment_intent_id,
            stripe_field(intent, "status"),
        )
        return False
    return mark_captured(card_hold_id, amount_cents=amount, payment_intent_id=payment_intent_id)


class _Cancel(str, enum.Enum):
    """How a cancel in Stripe ended."""

    CANCELED = "canceled"  # cancelled now, or never existed: no authorization
    WAS_CANCELED = "was_canceled"  # cancelled before this call: no authorization either
    SUCCEEDED = "succeeded"  # it was captured: never mark it released
    REFUSED = "refused"  # anything else; logged


GONE = (_Cancel.CANCELED, _Cancel.WAS_CANCELED)


def _cancel_payment_intent(
    payment_intent_id: str | None, card_hold_id: int
) -> tuple[_Cancel, Exception | None]:
    """Cancel a hold's PaymentIntent in Stripe. Stripe's transient errors propagate.

    Stripe's refusal names the PaymentIntent's status, so one call settles any state: a
    live authorization (``requires_capture``, even past its expiry) is cancelled, one
    missing counts as cancelled, one already ``canceled`` (by us, by Stripe when it
    lapsed, or by anyone else) is ``was_canceled``, and a ``succeeded`` one was captured.
    """
    if not payment_intent_id:
        return _Cancel.CANCELED, None
    try:
        utils.get_stripe().PaymentIntent.cancel(payment_intent_id)
    except stripe.InvalidRequestError as error:
        if getattr(error, "code", None) == "resource_missing":
            return _Cancel.CANCELED, None
        status = payment_intent_status_of(error, payment_intent_id)
        if status == "canceled":
            return _Cancel.WAS_CANCELED, error
        if status == "succeeded":
            return _Cancel.SUCCEEDED, error
        logger.error(
            "Stripe refused to cancel PaymentIntent %s of card hold %s",
            payment_intent_id,
            card_hold_id,
            exc_info=True,
        )
        return _Cancel.REFUSED, error
    return _Cancel.CANCELED, None


def _claim_for_release(
    card_hold_id: int, *, card_released: bool = False
) -> tuple["AbstractCardHold | None", bool, str]:
    """Decide, under the target's lock and then the hold's, whether to release the hold.

    Returns ``(hold, claimed, reason)``; ``hold`` is ``None`` when nothing may be
    cancelled: the hold is closed, or its target is alive and not cancelled (nor done
    with the card, when ``card_released``, with no charge in flight). A target that no
    longer exists counts as cancelled. An unlinked pending hold is claimed (marked
    released) here, so placing, which only links pending holds, can no longer link it
    while we cancel. ``reason`` is the ``ReleaseReason`` to record.

    A ``scheduled`` hold (or a ``saved`` card) holds nothing in Stripe: it is released
    here, under the locks, and confirmed, so the caller's cancel has no PaymentIntent to
    call Stripe for. One whose placement is under way is left to the placement, which
    settles it, and one a live :func:`capture` claims is left to that capture (the sweep
    retries it later).
    """
    CardHold = _holds()
    Reason = CardHold.ReleaseReason
    seen = (
        CardHold.objects.filter(pk=card_hold_id)
        .releasable()
        .select_related("target_document")
        .first()
    )
    if seen is None:
        return None, False, ""
    registered = None
    if seen.target_document_id is not None:
        registered = target_for_content_type_id(seen.target_document.content_type_id)
        if registered is None:
            logger.error("Card hold %s backs an unregistered target; not releasing it", seen.pk)
            return None, False, ""

    with transaction.atomic():
        alive = None
        if registered is not None:
            alive = registered[1].lock(seen.target_document.object_id)
        hold = CardHold.objects.select_for_update().filter(pk=card_hold_id).releasable().first()
        if hold is None:
            return None, False, ""
        if hold.capture_claimed_at and hold.capture_claimed_at > (
            timezone.now() - CAPTURE_CLAIM_TIMEOUT
        ):
            # capture() settles it, or the sweep retries once the claim is gone.
            logger.info("Card hold %s is being captured; not releasing it now", hold.pk)
            return None, False, ""
        if hold.status == CardHold.Status.SCHEDULED and hold.placement_key:
            logger.info("Card hold %s is being placed; the placement settles it", hold.pk)
            return None, False, ""
        if hold.target_document_id != seen.target_document_id:
            # Linked since it was read, so its target's lock wasn't taken: next time.
            logger.info("Card hold %s changed target meanwhile; not releasing it now", hold.pk)
            return None, False, ""
        reason = Reason.CANCELLED if hold.target_document_id is not None else Reason.ABANDONED
        if registered is not None and alive is not None:
            adapter = registered[1]
            if is_cancelled(adapter, alive.pk):
                reason = Reason.CANCELLED
            elif (
                card_released
                and is_card_released(adapter, alive.pk)
                and not adapter.charge_may_be_in_flight(alive)
            ):
                reason = Reason.CARD_RELEASED
            else:
                logger.info("Card hold %s backs an active target; not releasing it", hold.pk)
                return None, False, ""
        if hold.target_document_id is None and hold.status == CardHold.Status.PENDING:
            hold.status = CardHold.Status.RELEASED
            hold.release_reason = reason
            hold.save(update_fields=["status", "release_reason", "modified"])
            send_on_commit(card_hold_released, hold_id=hold.pk)
            return hold, True, reason
        if hold.status in CardHold.UNPLACED_STATUSES:
            _release_scheduled(hold.pk, reason)
            hold.refresh_from_db()
            return hold, True, reason
        return hold, False, reason


def release(
    card_hold_id: int,
    *,
    claimed: bool = False,
    card_released: bool = False,
    payment_intent_id: str | None = None,
) -> bool:
    """Release a hold: cancel its PaymentIntent, then mark it released and confirmed.

    A ``scheduled`` hold is released with no Stripe call (nothing is held yet). Only an
    open or scheduled hold is touched, and only when its target is cancelled (or gone, or
    done with the card when ``card_released``). ``claimed``: the caller already marked
    the hold released under its lock, so only the cancel (and its confirmation) is left.
    Stripe is always asked, even past the hold's expiry (:func:`_cancel_payment_intent`):
    an already-canceled or missing PaymentIntent counts as released; one Stripe reports
    ``succeeded`` is marked captured, with the amount received, never released. Stripe is
    called with no lock held; transient errors propagate for the caller to retry. Returns
    whether the hold is now released.

    ``payment_intent_id`` (claimed releases): the authorization the claim was for. If the
    row was re-armed since, only that old PaymentIntent is cancelled; the row is left
    alone.
    """
    if not utils.stripe_configured():
        return False
    reason = ""
    if claimed:
        hold = _holds().objects.filter(pk=card_hold_id).first()
        if hold is None:
            return False
        payment_intent_id = payment_intent_id or hold.stripe_payment_intent_id
        if hold.stripe_payment_intent_id != payment_intent_id:
            outcome, _error = _cancel_payment_intent(payment_intent_id, hold.pk)
            if outcome == _Cancel.SUCCEEDED:
                logger.error(
                    "Card hold %s: PaymentIntent %s, which it doesn't carry, was captured",
                    hold.pk,
                    payment_intent_id,
                )
            if outcome != _Cancel.REFUSED and payment_intent_id in (
                hold.stray_payment_intent_ids or []
            ):
                _forget_stray(hold.pk, payment_intent_id)
            return outcome in GONE
    else:
        hold, claimed, reason = _claim_for_release(card_hold_id, card_released=card_released)
        if hold is None:
            return False
        payment_intent_id = hold.stripe_payment_intent_id
    outcome, _error = _cancel_payment_intent(payment_intent_id, hold.pk)
    if outcome == _Cancel.SUCCEEDED:
        _record_capture_from_stripe(hold.pk, payment_intent_id)
        return False
    if outcome == _Cancel.REFUSED:
        return False
    mark_released(hold.pk, payment_intent_id, confirmed=True, reason=reason)
    return True


class _ForCharge(str, enum.Enum):
    RELEASED = "released"  # released by this call: nothing of ours is held, charge may follow
    CAPTURED = "captured"
    REFUSED = "refused"
    ELSEWHERE = "elsewhere"  # cancelled or released outside this call: never charge on top


def _cancelled_by_stripe(error: Exception | None, payment_intent_id: str) -> bool:
    """Whether a PaymentIntent found ``canceled`` was cancelled by Stripe itself when its
    authorization lapsed (``cancellation_reason`` ``expired``, ``automatic`` before basil),
    rather than by someone who may have charged the card instead. Read from Stripe's
    error, else from Stripe."""
    intent = stripe_field(getattr(error, "error", None), "payment_intent")
    reason = stripe_field(intent, "cancellation_reason")
    if reason is None:
        reason = stripe_field(retrieve_payment_intent(payment_intent_id), "cancellation_reason")
    return reason in LAPSED_CANCELLATION_REASONS


def _block_charge(card_hold_id: int, block: str) -> bool:
    """Record that a capture refused to charge the hold, so no later :func:`capture`
    charges it on its own (``charge_blocked_reason``); whether this call recorded it."""
    return bool(
        _holds()
        .objects.filter(pk=card_hold_id, charged_at__isnull=True, charge_blocked_reason="")
        .update(charge_blocked_reason=block, modified=timezone.now())
    )


def _cancelled_elsewhere(card_hold_id: int, payment_intent_id: str | None) -> None:
    """The authorization was cancelled outside the card hold services, by someone who
    may have charged the card instead: released ``lapsed`` (confirmed) and blocked."""
    CardHold = _holds()
    mark_released(
        card_hold_id, payment_intent_id, confirmed=True, reason=CardHold.ReleaseReason.LAPSED
    )
    _block_charge(card_hold_id, CardHold.ChargeBlock.LAPSED)
    logger.warning(
        "Card hold %s: PaymentIntent %s was cancelled outside capture(); never charged on top",
        card_hold_id,
        payment_intent_id,
    )


def _release_for_charge(
    hold: "AbstractCardHold", reason: str, *, charge_key: str = ""
) -> tuple[_ForCharge, Any]:
    """Release an open hold no money will be taken from. Returns the outcome and, for
    ``captured`` the PaymentIntent, for ``refused`` Stripe's error.

    Stripe is asked even for a hold past its expiry: it may have been captured (a
    capture that answered late), and then it is recorded captured, never released, and
    nothing is charged on top; a live authorization is cancelled before anything is
    charged. ``charge_key`` claims the charge in the same UPDATE that releases the hold.

    ``released`` only when this call's UPDATE released the row, and the PaymentIntent
    was cancelled now, was missing, or was cancelled by Stripe when it lapsed. One found
    cancelled by anyone else, or a row another call released meanwhile, is
    ``elsewhere``: never charge on top of it.
    """
    payment_intent_id = hold.stripe_payment_intent_id
    outcome, error = _cancel_payment_intent(payment_intent_id, hold.pk)
    if outcome == _Cancel.SUCCEEDED:
        return _ForCharge.CAPTURED, _record_capture_from_stripe(hold.pk, payment_intent_id)
    if outcome == _Cancel.REFUSED:
        return _ForCharge.REFUSED, error
    if outcome == _Cancel.WAS_CANCELED and not _cancelled_by_stripe(error, payment_intent_id):
        _cancelled_elsewhere(hold.pk, payment_intent_id)
        return _ForCharge.ELSEWHERE, error
    if not mark_released(
        hold.pk, payment_intent_id, confirmed=True, reason=reason, charge_key=charge_key
    ):
        logger.warning("Card hold %s was released by another call meanwhile", hold.pk)
        return _ForCharge.ELSEWHERE, None
    return _ForCharge.RELEASED, None


def _released_for_charge(hold: "AbstractCardHold") -> bool:
    """Released ``for_charge`` and confirmed, by :func:`release_for_charge` (no charge
    claim, and no refused one: :func:`capture` never tried to charge it)."""
    CardHold = type(hold)
    return (
        hold.status == CardHold.Status.RELEASED
        and hold.release_reason == CardHold.ReleaseReason.FOR_CHARGE
        and hold.release_confirmed_at is not None
        and not hold.charge_key
        and not hold.charge_generation
    )


def release_for_charge(card_hold_id: int) -> bool:
    """Release a hold no money will be taken from, whatever its target's state.

    For right before the final amount is charged afresh on the card by the caller (it is
    above the amount held, or the hold expired), so the customer is never charged twice;
    and for a target settled without the hold. Never captures; a PaymentIntent Stripe
    reports captured is recorded as such. Stripe's transient errors propagate; any other
    refusal is logged and the hold left to lapse.

    Returns whether the hold is released for the caller's charge: charge afresh only
    then. ``True`` for a hold this call, or an earlier one, released ``for_charge``;
    ``False`` for anything else, including a PaymentIntent found cancelled by someone
    else, a hold :func:`capture` charged or refused to charge, and a hold being captured
    right now: it takes the same claim as :func:`capture`, so the two never run at once.

    The hold is recorded released ``for_charge``: it is never re-armed, and a later
    :func:`capture` of it charges nothing (the caller charges). A ``scheduled`` (or
    ``saved``) hold is released with no Stripe call, unless its placement is under way
    (``False``: retry); so is one released to go back to ``scheduled`` (``rescheduled``,
    ``not_holdable``) once Stripe confirmed its cancel (``False`` until then). Raises :class:`CardHoldInTransaction` inside a transaction: the
    claim must commit before Stripe is called.
    """
    _ensure_outside_transaction()
    CardHold = _holds()
    claimed_at = _claim_capture(card_hold_id)
    if claimed_at is None:
        logger.info("Card hold %s is being captured (or doesn't exist); not released", card_hold_id)
        return False
    try:
        hold = CardHold.objects.get(pk=card_hold_id)
        if hold.status in CardHold.UNPLACED_STATUSES:
            return _release_scheduled(hold.pk, CardHold.ReleaseReason.FOR_CHARGE)
        if hold.status in CardHold.OPEN_STATUSES:
            outcome, _detail = _release_for_charge(hold, CardHold.ReleaseReason.FOR_CHARGE)
            return outcome == _ForCharge.RELEASED
        if hold.release_reason in CardHold.BACK_TO_SCHEDULED_REASONS:
            # On its way back to scheduled: nothing of ours is held once Stripe confirmed
            # the cancel (until then, retry), and nobody charged.
            return bool(
                CardHold.objects.filter(
                    pk=hold.pk,
                    status=CardHold.Status.RELEASED,
                    release_reason=hold.release_reason,
                    release_confirmed_at__isnull=False,
                    charge_key="",
                    charge_generation=0,
                ).update(release_reason=CardHold.ReleaseReason.FOR_CHARGE, modified=timezone.now())
            )
        return _released_for_charge(hold)
    finally:
        _release_capture_claim(card_hold_id, claimed_at)


def _capturable(hold: "AbstractCardHold", amount_cents: int) -> bool:
    return (
        hold.status == type(hold).Status.AUTHORIZED
        and hold.expires_at is not None
        and not _expired(hold)
        and 0 < amount_cents <= hold.amount_cents
    )


def capturable_hold(card_hold_id: int, amount_cents: int) -> "AbstractCardHold | None":
    """The hold, when ``amount_cents`` can be captured from it: it is ``authorized``, not
    past its expiry, and ``0 < amount_cents <= amount held``. Reads the database only."""
    hold = _holds().objects.filter(pk=card_hold_id).first()
    return hold if hold is not None and _capturable(hold, amount_cents) else None


class CaptureStatus(str, enum.Enum):
    """How :func:`capture` took the money.

    - ``captured``: from the hold, exactly the amount asked (now, or by an earlier call:
      never twice).
    - ``paid``: the amount is above a live hold: the hold was captured in full, then the
      difference was charged to the same card, off-session (two payments, now or by an
      earlier call: never twice). ``payment_intent`` is the difference's when this call
      charged it.
    - ``partially_paid``: as ``paid``, but the card refused the difference (``error``):
      the held amount stays taken and the rest is due (``difference_charge_failed`` was
      sent). A later call for the same amount charges the difference again, with a new
      key; :func:`mark_paid_outside` records it paid instead.
    - ``charged``: ``charge()`` ran once (its result is ``CaptureResult.charge``), for the
      full amount: the hold couldn't be captured (expired, lapsed, released to be
      rescheduled) and this call released it, or it never authorized anything (a
      ``scheduled`` hold, a ``saved`` card, a failed hold staff kept). A repeated call
      answers ``charged`` from the database, with ``charge`` ``None``, and never charges
      again.
    - ``declined``: the card declined. Declining the capture, nothing is charged, then or
      on a retry. Declining ``charge()`` (Stripe refused it for good: a ``CardError`` or a
      non-409 ``InvalidRequestError``, in ``error``), nothing was taken, and the next call
      charges again with a new key (after the customer adds another card, say).
    - ``nothing_due``: asked for 0. The hold is released and nothing is charged (also on
      a retry); the target is ``paid``, as nothing is owed. Never while the release is
      under way (``in_progress``), nor for a charge an earlier call claimed and never
      finished (``in_progress``, below).
    - ``in_progress``: another capture of this hold is running, or its placement or
      reschedule is under way. Retry later. Also asked for 0 while a charge an earlier
      call claimed never finished (it may have run): it is not re-run, and an error is
      logged for you to settle it with Stripe by hand.
    - ``not_captured``: nothing was taken by this call, and a retry won't charge either:
      decide by hand. Stripe refused to release the hold (``error``), so charging on top
      could take the money twice; the capture didn't succeed; the hold was captured
      earlier for another amount (``payment_intent``); the capture's idempotency key was
      used with other parameters; the hold was released outside this call (by
      :func:`release_for_charge`, whose caller charges, by staff, or with its target);
      the authorization was cancelled in Stripe by someone else, who may have charged;
      an earlier call declined or refused (``charge_blocked_reason``); a charge Stripe
      refused before whose target was cancelled (or deleted) since; a charge that never
      finished is older than Stripe keeps its key; or there is no such hold.
    """

    CAPTURED = "captured"
    PAID = "paid"
    PARTIALLY_PAID = "partially_paid"
    CHARGED = "charged"
    DECLINED = "declined"
    IN_PROGRESS = "in_progress"
    NOT_CAPTURED = "not_captured"
    NOTHING_DUE = "nothing_due"


@dataclass
class CaptureResult:
    status: CaptureStatus
    payment_intent: Any = None
    charge: Any = None
    error: Exception | None = None


def capture_idempotency_key(hold: "AbstractCardHold") -> str:
    """One capture per authorization: a re-armed hold gets a new key with its new
    PaymentIntent."""
    return f"{key_prefix()}-capture-{hold.stripe_payment_intent_id}"


def charge_idempotency_key(card_hold_id: int, generation: int = 0) -> str:
    """The key :func:`capture` hands the project's ``charge``: one charge per hold (a hold
    charged instead is never re-armed) and ``generation`` (``charge_generation``). A
    charge Stripe definitely refused bumps the generation, so the next one gets a new key
    instead of Stripe replaying that refusal for 24 hours."""
    return f"{key_prefix()}-charge-{card_hold_id}-{generation}"


def _charge_key(hold: "AbstractCardHold") -> str:
    return charge_idempotency_key(hold.pk, hold.charge_generation)


def _claim_capture(card_hold_id: int) -> datetime.datetime | None:
    """Claim the hold for one capture call (a conditional UPDATE, committed at once);
    the claim's timestamp, or ``None`` when another live call holds it (or no row)."""
    now = timezone.now()
    claimed = (
        _holds()
        .objects.filter(pk=card_hold_id)
        .filter(
            Q(capture_claimed_at__isnull=True)
            | Q(capture_claimed_at__lt=now - CAPTURE_CLAIM_TIMEOUT)
        )
        .update(capture_claimed_at=now)
    )
    return now if claimed else None


def _release_capture_claim(card_hold_id: int, claimed_at: datetime.datetime) -> None:
    _holds().objects.filter(pk=card_hold_id, capture_claimed_at=claimed_at).update(
        capture_claimed_at=None
    )


def capture(
    card_hold_id: int,
    amount_cents: int,
    *,
    charge: Callable[..., Any],
    idempotency_key: str | None = None,
) -> CaptureResult:
    """Take ``amount_cents`` once: capture the hold when it covers it; above a live hold,
    capture all of it and charge the difference; else charge the full amount.

    The entry point at the target's date for every target, with a hold or without one
    (a ``saved`` card: ``charge`` runs, once). One charge, never two:

    - the call first claims the hold (a conditional UPDATE, before any Stripe call); a
      concurrent call, or :func:`release_for_charge`, answers ``in_progress`` (``False``)
      and touches nothing;
    - a hold already ``captured`` answers ``captured`` again when it was for
      ``amount_cents`` (``not_captured`` otherwise), and ``charge`` never runs;
    - above an authorized, unexpired hold, the hold is captured in full first (so a
      refused difference never costs the held amount), then the difference is charged
      off-session to the hold's card by this module (:func:`_charge_difference`, key
      ``{prefix}-difference-{hold}-{n}``, claimed before it is sent): ``paid``, or
      ``partially_paid`` when the card refuses it. ``charge`` never runs on this path. A
      repeated call for the same amount answers from the database, resumes a difference
      that got no usable answer with the same key, or charges a refused one again with
      the next key;
    - ``charge`` runs only from these states: an open hold this call releases (Stripe
      confirms the cancel, or the authorization lapsed by itself); a ``scheduled`` hold
      never placed, a ``saved`` card, or a hold released to be rescheduled; a failed hold
      staff kept; or a charge this call's predecessor claimed and didn't finish. Every
      other state answers ``not_captured`` and charges nothing, now and on any retry: a
      hold released outside this call, an authorization someone else cancelled in
      Stripe, a capture the card declined (``charge_blocked_reason``);
    - ``charge`` is called as ``charge(idempotency_key=...)``, with
      :func:`charge_idempotency_key` (``{prefix}-charge-{hold}-{n}``): pass it to Stripe. The key is recorded (with when)
      before ``charge`` runs and ``charged_at`` once it returns; a repeated call answers
      ``charged`` from the database. A charge that raised (or a process that died
      mid-charge) is run again by the next call with the same key, so Stripe replays it
      instead of charging twice; but Stripe keeps a key only 24 hours, so a claim older
      than :data:`CHARGE_KEY_TTL` is never re-run: ``not_captured``, logged as an error,
      for you to reconcile with Stripe by hand;
    - a release Stripe refuses answers ``not_captured`` with the error, and nothing is
      charged;
    - no hold row with this id: ``not_captured``, nothing charged.

    - ``charge`` raising a definite refusal (``CardError``, a non-409
      ``InvalidRequestError``) answers ``declined``: the claim is dropped and the key's
      generation bumped, so the next call charges with a new key. Any other error (no
      usable answer: a connection error, a 5xx, a 429, a 409, a bad key) propagates and
      keeps the claim and its key;
    - ``amount_cents`` 0 releases the hold and charges nothing (``nothing_due``); with a
      charge claimed earlier that never finished, ``charge`` isn't re-run: ``in_progress``,
      logged as an error, the claim left as it is. A negative amount raises ``ValueError``.

    ``idempotency_key`` defaults to ``{prefix}-capture-{PaymentIntent}``, one per
    authorization; reuse it to resume an interrupted capture. Stripe's transient errors
    propagate. Raises :class:`CardHoldInTransaction` inside a transaction: the claims
    must commit before Stripe is called.
    """
    if amount_cents < 0:
        raise ValueError(f"capture() of card hold {card_hold_id}: amount_cents is negative")
    _ensure_outside_transaction()
    CardHold = _holds()
    claimed_at = _claim_capture(card_hold_id)
    if claimed_at is None:
        if CardHold.objects.filter(pk=card_hold_id).exists():
            return CaptureResult(CaptureStatus.IN_PROGRESS)
        # No row: nothing to claim on, and no record of what this id was. Charging blind
        # could charge a target twice.
        logger.error("capture() of card hold %s: no such hold; nothing charged", card_hold_id)
        return CaptureResult(CaptureStatus.NOT_CAPTURED)
    try:
        hold = CardHold.objects.get(pk=card_hold_id)
        return _capture_claimed(hold, amount_cents, charge=charge, idempotency_key=idempotency_key)
    finally:
        _release_capture_claim(card_hold_id, claimed_at)


def _captured(
    intent: Any, amount_cents: int, *, recorded_cents: int | None = None
) -> CaptureResult:
    """``captured`` when what the hold was captured for is ``amount_cents`` (or can't be
    told); ``not_captured`` when it was another amount: this call took nothing."""
    received = recorded_cents
    if received is None and intent is not None:
        received = stripe_field(intent, "amount_received")
    if received and received != amount_cents:
        logger.warning(
            "PaymentIntent %s was captured for %s, not the %s asked",
            stripe_id(intent),
            received,
            amount_cents,
        )
        return CaptureResult(CaptureStatus.NOT_CAPTURED, payment_intent=intent)
    return CaptureResult(CaptureStatus.CAPTURED, payment_intent=intent)


def _capture_claimed(
    hold: "AbstractCardHold",
    amount_cents: int,
    *,
    charge: Callable[..., Any],
    idempotency_key: str | None,
) -> CaptureResult:
    """:func:`capture`, under the capture claim, with ``hold`` read after claiming it."""
    CardHold = type(hold)
    if hold.status == CardHold.Status.CAPTURED:
        if hold.difference_amount_cents:
            # Captured in full for an amount above the hold: the difference is settled
            # (or still due) on its own claim.
            return _settle_difference(hold, amount_cents)
        # The amount recorded answers it; Stripe is read only when none was.
        intent = None
        if hold.captured_amount_cents is None and hold.stripe_payment_intent_id:
            intent = retrieve_payment_intent(hold.stripe_payment_intent_id)
        return _captured(intent, amount_cents, recorded_cents=hold.captured_amount_cents)
    if hold.charge_key:
        if amount_cents == 0 and hold.charged_at is None and not hold.charge_blocked_reason:
            # Nothing is due now, but a charge was claimed and never answered: running it
            # again would take money, and dropping it would hide one that may have run.
            logger.error(
                "capture() of card hold %s for 0: its charge (key %s) never finished and may"
                " have run; not re-run. Check Stripe and settle it by hand.",
                hold.pk,
                hold.charge_key,
            )
            return CaptureResult(CaptureStatus.IN_PROGRESS)
        # Charged instead before (answered from the database), or a charge to resume.
        return _charge_once(hold.pk, charge, amount_cents)
    if hold.charge_blocked_reason:
        logger.warning(
            "Card hold %s: an earlier capture refused to charge it (%s); not charging",
            hold.pk,
            hold.charge_blocked_reason,
        )
        return CaptureResult(CaptureStatus.NOT_CAPTURED)
    if amount_cents == 0:
        return _nothing_due(hold)
    if hold.charge_generation:
        return _charge_again(hold, charge, amount_cents)
    if hold.status == CardHold.Status.RELEASED:
        return _charge_released(hold, charge, amount_cents)
    if hold.status == CardHold.Status.FAILED and hold.kept_at is None:
        logger.warning("Card hold %s failed and staff haven't kept it; not charging", hold.pk)
        return CaptureResult(CaptureStatus.NOT_CAPTURED)
    if _above_live_hold(hold, amount_cents):
        return _capture_above_hold(
            hold, amount_cents, charge=charge, idempotency_key=idempotency_key
        )
    if not _capturable(hold, amount_cents):
        return _charge_instead(hold, amount_cents, charge)
    if not _ask_capture(hold, amount_cents):
        return CaptureResult(CaptureStatus.IN_PROGRESS)
    return _capture_from_hold(hold, amount_cents, charge=charge, idempotency_key=idempotency_key)


def _ask_capture(
    hold: "AbstractCardHold", amount_cents: int, *, difference: int | None = None
) -> bool:
    """Before a capture of ``hold`` is sent (a conditional UPDATE, committed first): record
    the final amount asked (``requested_amount_cents``), that a capture was sent
    (``capture_sent_at``, the first time), and the ``difference`` planned above the hold.

    Within the hold (no ``difference``), a plan an earlier call made is dropped only when
    no capture was ever sent: one sent for the whole hold may still have run, and its
    answer (the webhook) must still find it, so a capture for this other amount is never
    taken as ``paid`` (:func:`mark_captured`). ``False`` when the row moved on (no longer
    this authorization, or captured meanwhile)."""
    CardHold = type(hold)
    now = timezone.now()
    changes: dict[str, Any] = {
        "requested_amount_cents": amount_cents,
        "capture_sent_at": hold.capture_sent_at or now,
        "modified": now,
    }
    if difference is not None:
        changes["difference_amount_cents"] = difference
    elif hold.capture_sent_at is None:
        changes["difference_amount_cents"] = None
    if not CardHold.objects.filter(
        pk=hold.pk,
        status=CardHold.Status.AUTHORIZED,
        stripe_payment_intent_id=hold.stripe_payment_intent_id,
        capture_sent_at=hold.capture_sent_at,
    ).update(**changes):
        return False
    hold.requested_amount_cents = amount_cents
    hold.capture_sent_at = changes["capture_sent_at"]
    hold.difference_amount_cents = changes.get(
        "difference_amount_cents", hold.difference_amount_cents
    )
    return True


def _above_live_hold(hold: "AbstractCardHold", amount_cents: int) -> bool:
    """Whether ``amount_cents`` is above an authorization that can still be captured: the
    hold is captured in full and the rest charged on top (:func:`_capture_above_hold`).
    An expired (or never-expiring, unknown) one is charged afresh instead."""
    return (
        hold.status == type(hold).Status.AUTHORIZED
        and hold.expires_at is not None
        and not _expired(hold)
        and amount_cents > hold.amount_cents
    )


def _capture_above_hold(
    hold: "AbstractCardHold",
    amount_cents: int,
    *,
    charge: Callable[..., Any],
    idempotency_key: str | None,
) -> CaptureResult:
    """``amount_cents`` is above a live hold: plan the difference on the row, capture the
    whole hold, then charge the difference (:func:`_settle_difference`).

    The plan is written before the capture is sent, so whatever records the capture
    later (this call, a retry, the webhook) knows a difference is still due and doesn't
    call the target ``paid`` yet. A capture that doesn't go through answers as
    :func:`_capture_from_hold` does: a decline is never followed by any charge, and a
    lapsed authorization is charged the full amount through ``charge``."""
    if not _ask_capture(hold, amount_cents, difference=amount_cents - hold.amount_cents):
        return CaptureResult(CaptureStatus.IN_PROGRESS)
    captured = _capture_from_hold(
        hold, hold.amount_cents, charge=charge, idempotency_key=idempotency_key
    )
    if captured.status != CaptureStatus.CAPTURED:
        return captured
    hold.refresh_from_db()
    return _settle_difference(hold, amount_cents)


def _capture_from_hold(
    hold: "AbstractCardHold",
    amount_cents: int,
    *,
    charge: Callable[..., Any],
    idempotency_key: str | None,
) -> CaptureResult:
    """Capture ``amount_cents`` from a hold that covers it (:func:`_capturable`), under
    the capture claim; a lapsed authorization is charged instead. Stripe's fee for the
    capture is recorded when its balance transaction is ready (else the sweep fills it)."""
    CardHold = type(hold)
    payment_intent_id = hold.stripe_payment_intent_id
    key = idempotency_key or capture_idempotency_key(hold)
    try:
        intent = utils.get_stripe().PaymentIntent.capture(
            payment_intent_id,
            amount_to_capture=amount_cents,
            expand=FEE_EXPAND,
            idempotency_key=key,
        )
    except stripe.CardError as error:
        # Blocked first: a retry after a release that didn't go through (an expired hold,
        # say) must not charge instead.
        _block_charge(hold.pk, CardHold.ChargeBlock.DECLINED)
        try:
            _release_for_charge(hold, CardHold.ReleaseReason.DECLINED)
        except stripe.StripeError:
            logger.warning("Couldn't release declined card hold %s", hold.pk, exc_info=True)
        return CaptureResult(CaptureStatus.DECLINED, error=error)
    except stripe.IdempotencyError as error:
        # The key was used with other parameters (another amount, another PaymentIntent):
        # Stripe ran nothing for this request.
        logger.warning("Capture of card hold %s refused: key %s reused", hold.pk, key)
        return CaptureResult(CaptureStatus.NOT_CAPTURED, error=error)
    except stripe.InvalidRequestError as error:
        status = payment_intent_status_of(error, payment_intent_id)
        if status == "succeeded":
            # Captured already (this attempt, answered earlier).
            intent = retrieve_payment_intent(payment_intent_id)
        elif getattr(error, "code", None) in LAPSED_AUTHORIZATION_CODES or (
            status == "canceled" and _cancelled_by_stripe(error, payment_intent_id)
        ):
            # The authorization lapsed: no money moved, and none can be taken from it.
            if not mark_released(
                hold.pk,
                payment_intent_id,
                confirmed=True,
                reason=CardHold.ReleaseReason.FOR_CHARGE,
                charge_key=_charge_key(hold),
            ):
                logger.warning("Card hold %s was released by another call meanwhile", hold.pk)
                return CaptureResult(CaptureStatus.NOT_CAPTURED, error=error)
            # Nothing was captured: the full amount is charged, so no difference is due.
            CardHold.objects.filter(pk=hold.pk).update(difference_amount_cents=None)
            return _charge_once(hold.pk, charge, hold.requested_amount_cents or amount_cents)
        elif status == "canceled":
            # Cancelled in Stripe by someone else, who may have charged the card instead:
            # charging on top could take the money twice, so never, nor on a retry.
            _cancelled_elsewhere(hold.pk, payment_intent_id)
            return CaptureResult(CaptureStatus.NOT_CAPTURED, error=error)
        else:
            raise
    if stripe_field(intent, "status") != "succeeded":
        return CaptureResult(CaptureStatus.NOT_CAPTURED, payment_intent=intent)
    mark_captured(
        hold.pk,
        amount_cents=stripe_field(intent, "amount_received") or amount_cents,
        payment_intent_id=payment_intent_id,
    )
    _store_fee(hold.pk, "capture_fee_cents", intent)
    return _captured(intent, amount_cents)


def _charge_released(
    hold: "AbstractCardHold", charge: Callable[..., Any], amount_cents: int
) -> CaptureResult:
    """A ``released`` hold with no charge claim. Only one released to go back to
    ``scheduled`` (``rescheduled``, ``not_holdable``), its cancel confirmed, is charged
    (nothing of ours is held, and nobody else charged); while the cancel is unconfirmed
    (the authorization may still be live), ``in_progress``. Any other release happened outside this
    call, which may have charged: ``not_captured``."""
    CardHold = type(hold)
    Reason = CardHold.ReleaseReason
    if hold.release_reason in CardHold.BACK_TO_SCHEDULED_REASONS:
        if hold.release_confirmed_at is None:
            return CaptureResult(CaptureStatus.IN_PROGRESS)
        now = timezone.now()
        claimed = CardHold.objects.filter(
            pk=hold.pk,
            status=CardHold.Status.RELEASED,
            release_reason=hold.release_reason,
            release_confirmed_at__isnull=False,
            charge_key="",
        ).update(
            release_reason=Reason.FOR_CHARGE,
            charge_key=_charge_key(hold),
            charge_claimed_at=now,
            modified=now,
        )
        if not claimed:
            return CaptureResult(CaptureStatus.IN_PROGRESS)
        return _charge_once(hold.pk, charge, amount_cents)
    if hold.release_reason == Reason.FOR_CHARGE:
        logger.warning(
            "Card hold %s was released for a charge made outside capture(); not charging",
            hold.pk,
        )
    else:
        logger.warning(
            "Card hold %s was released (%s) outside capture(); not charging",
            hold.pk,
            hold.release_reason or "no reason",
        )
    return CaptureResult(CaptureStatus.NOT_CAPTURED)


def _charge_instead(
    hold: "AbstractCardHold", amount_cents: int, charge: Callable[..., Any]
) -> CaptureResult:
    """The hold can't cover the amount (or never held anything): release it, then charge
    once, or say why not.

    A ``scheduled`` hold or a ``saved`` card is released first with no Stripe call
    (``in_progress`` while a placement is under way, which could still authorize). A
    failed hold staff kept holds nothing. An open hold is cancelled in Stripe first, and
    charged only when this call released it (:func:`_release_for_charge`). Each claims
    the charge (``charge_key``) in the statement that settles the hold.
    """
    CardHold = type(hold)
    charge_key = _charge_key(hold)
    if hold.status == CardHold.Status.FAILED:
        now = timezone.now()
        if not CardHold.objects.filter(
            pk=hold.pk, status=CardHold.Status.FAILED, kept_at__isnull=False, charge_key=""
        ).update(charge_key=charge_key, charge_claimed_at=now, modified=now):
            return CaptureResult(CaptureStatus.NOT_CAPTURED)
        return _charge_once(hold.pk, charge, amount_cents)
    if hold.status in CardHold.UNPLACED_STATUSES:
        if not _release_scheduled(
            hold.pk, CardHold.ReleaseReason.FOR_CHARGE, charge_key=charge_key
        ):
            return CaptureResult(CaptureStatus.IN_PROGRESS)
        return _charge_once(hold.pk, charge, amount_cents)
    outcome, detail = _release_for_charge(
        hold, CardHold.ReleaseReason.FOR_CHARGE, charge_key=charge_key
    )
    if outcome == _ForCharge.CAPTURED:
        return _captured(detail, amount_cents)
    if outcome == _ForCharge.REFUSED:
        return CaptureResult(CaptureStatus.NOT_CAPTURED, error=detail)
    if outcome == _ForCharge.ELSEWHERE:
        return CaptureResult(CaptureStatus.NOT_CAPTURED, error=detail)
    return _charge_once(hold.pk, charge, amount_cents)


def _charge_once(
    card_hold_id: int, charge: Callable[..., Any], amount_cents: int | None = None
) -> CaptureResult:
    """Run the project's ``charge`` at most once per hold, under the capture claim.

    ``amount_cents`` (what :func:`capture` was asked for) is recorded as
    ``charge_amount_cents`` before the charge first runs with its key, so the payment
    totals count it even when ``charge`` returns something other than a PaymentIntent; a
    resumed charge keeps the amount its key was first sent for.

    Only for a hold whose charge claim (``charge_key``, with ``charge_claimed_at``) the
    caller wrote in the statement that allowed the charge; without one nothing is
    charged. A hold already charged (``charged_at``) answers ``charged`` from the
    database, with ``charge`` ``None``, and never runs it again. A key without
    ``charged_at`` is a charge that raised or never finished: ``charge`` runs again with
    that same key, so Stripe replays the first charge instead of making a second; unless
    the claim is older than :data:`CHARGE_KEY_TTL` (Stripe may have forgotten the key),
    then it is blocked (``stale_charge``) and logged as an error: ``not_captured``.

    Only a claim whose charge got no usable answer is kept that way. One Stripe
    definitely refused (:func:`_drop_refused_charge`) answers ``declined``, and the next
    call charges again with a new key.
    """
    CardHold = _holds()
    key, claimed_at, charged_at, blocked = (
        CardHold.objects.filter(pk=card_hold_id)
        .values_list("charge_key", "charge_claimed_at", "charged_at", "charge_blocked_reason")
        .get()
    )
    if charged_at is not None:
        return CaptureResult(CaptureStatus.CHARGED)
    if not key or blocked:
        return CaptureResult(CaptureStatus.NOT_CAPTURED)
    if claimed_at is None or claimed_at < timezone.now() - CHARGE_KEY_TTL:
        _block_charge(card_hold_id, CardHold.ChargeBlock.STALE_CHARGE)
        logger.error(
            "Card hold %s: its charge (key %s, claimed %s) got no usable answer and is older"
            " than Stripe keeps the key; not re-run, as it might charge twice. Check Stripe"
            " and settle it by hand.",
            card_hold_id,
            key,
            claimed_at or "at an unknown time",
        )
        return CaptureResult(CaptureStatus.NOT_CAPTURED)
    if amount_cents is not None:
        CardHold.objects.filter(
            pk=card_hold_id, charge_key=key, charged_at__isnull=True, charge_amount_cents=None
        ).update(charge_amount_cents=amount_cents)
    try:
        result = charge(idempotency_key=key)
    except (stripe.CardError, stripe.InvalidRequestError) as error:
        if getattr(error, "http_status", None) == 409:
            raise
        _drop_refused_charge(card_hold_id, key, error)
        return CaptureResult(CaptureStatus.DECLINED, error=error)
    except stripe.IdempotencyError:
        # The key's first request may have charged: only Stripe can tell. Kept.
        logger.error(
            "Card hold %s: Stripe refused the charge key %s as reused with other parameters;"
            " the first charge with it may have run. Check Stripe.",
            card_hold_id,
            key,
        )
        raise
    _record_charge(card_hold_id, result)
    return CaptureResult(CaptureStatus.CHARGED, charge=result)


def _record_charge(card_hold_id: int, result: Any) -> None:
    """The project's ``charge`` returned: record ``charged_at`` and, when it returned the
    PaymentIntent, its id, amount (else the amount asked stays, recorded at claim time)
    and (when its balance transaction was expanded) Stripe's fee; the target is ``paid``.
    Without a fee, the sweep reads it later."""
    CardHold = _holds()
    changes: dict[str, Any] = {"charged_at": timezone.now()}
    payment_intent_id = stripe_id(result) if isinstance(result, dict) else None
    if payment_intent_id and str(payment_intent_id).startswith("pi_"):
        changes["charge_payment_intent_id"] = payment_intent_id
        amount = stripe_field(result, "amount_received") or stripe_field(result, "amount")
        if amount is not None:
            changes["charge_amount_cents"] = amount
    CardHold.objects.filter(pk=card_hold_id, charged_at__isnull=True).update(**changes)
    if "charge_payment_intent_id" in changes:
        _store_fee(card_hold_id, "charge_fee_cents", result)
    _set_payment_status(
        card_hold_id,
        CardHold.PaymentStatus.PAID,
        (CardHold.PaymentStatus.UNPAID,),
        q=Q(charged_at__isnull=False),
    )


def _drop_refused_charge(card_hold_id: int, key: str, error: Exception) -> None:
    """Stripe definitely refused the charge claimed with ``key``: nothing was taken. The
    claim is dropped and ``charge_generation`` bumped in one statement, so the next
    :func:`capture` charges with a new key instead of Stripe replaying this refusal (it
    saves the first answer for the key, errors included, for 24 hours)."""
    _holds().objects.filter(pk=card_hold_id, charge_key=key, charged_at__isnull=True).update(
        charge_key="",
        charge_claimed_at=None,
        charge_amount_cents=None,
        charge_generation=F("charge_generation") + 1,
        modified=timezone.now(),
    )
    logger.warning(
        "Card hold %s: the charge with key %s was refused (%s); the next capture() charges"
        " with a new key",
        card_hold_id,
        key,
        type(error).__name__,
    )


def _charge_again(
    hold: "AbstractCardHold", charge: Callable[..., Any], amount_cents: int
) -> CaptureResult:
    """A hold whose last charge Stripe refused (``charge_generation``): it was settled for
    that charge then, so nothing of ours is held. The charge is claimed again, with the
    next key, in a conditional UPDATE (``in_progress`` when the row moved on).

    The refused charge settled the hold, so :func:`release` and the sweep no longer touch
    it when its target is cancelled: the target is re-checked here, under its lock and
    then the hold's, and a cancelled (or deleted) target answers ``not_captured`` with
    nothing charged."""
    CardHold = type(hold)
    # None: unlinked (its target was deleted) or no longer registered; neither is charged.
    adapter = registered[1] if (registered := _registered(hold)) is not None else None
    with transaction.atomic():
        target = adapter.lock(hold.target_document.object_id) if adapter is not None else None
        CardHold.objects.select_for_update().filter(pk=hold.pk).first()
        if (
            adapter is None
            or _why_not_holdable(adapter, target) == CardHold.ReleaseReason.CANCELLED
        ):
            logger.warning(
                "Card hold %s: its target was cancelled after a refused charge; not charging",
                hold.pk,
            )
            return CaptureResult(CaptureStatus.NOT_CAPTURED)
        now = timezone.now()
        if not CardHold.objects.filter(
            pk=hold.pk,
            charge_key="",
            charge_generation=hold.charge_generation,
            charged_at__isnull=True,
            charge_blocked_reason="",
        ).update(charge_key=_charge_key(hold), charge_claimed_at=now, modified=now):
            return CaptureResult(CaptureStatus.IN_PROGRESS)
    return _charge_once(hold.pk, charge, amount_cents)


def _nothing_due(hold: "AbstractCardHold") -> CaptureResult:
    """:func:`capture` of 0: release the hold (:func:`_release_nothing_due`) and, once it
    answers ``nothing_due``, mark the target ``paid``: nothing is owed. One conditional
    UPDATE, only from ``unpaid``, only on a ``released`` row with no charge claimed or
    taken; ``payment_status_changed`` is sent after the commit. Any other answer
    (``in_progress``, ``not_captured``) leaves it as it is. ``partially_paid`` never
    reaches here: it is only on a hold captured in full, which answers before."""
    result = _release_nothing_due(hold)
    if result.status == CaptureStatus.NOTHING_DUE:
        CardHold = type(hold)
        _set_payment_status(
            hold.pk,
            CardHold.PaymentStatus.PAID,
            (CardHold.PaymentStatus.UNPAID,),
            q=Q(status=CardHold.Status.RELEASED, charge_key="", charged_at__isnull=True),
        )
    return result


def _release_nothing_due(hold: "AbstractCardHold") -> CaptureResult:
    """:func:`capture` of 0: release the hold (``card_released``) and charge nothing.

    ``nothing_due`` once nothing of ours is held: an open hold cancelled in Stripe, a
    scheduled hold or saved card, a failed hold staff kept, a hold released to go back to
    ``scheduled`` (its cancel confirmed), or any other released hold. ``in_progress``
    while a placement, or a cancel Stripe hasn't confirmed, is under way;
    ``not_captured`` for a failed hold staff haven't decided, a release Stripe refused,
    an authorization cancelled by someone else, or one found captured."""
    CardHold = type(hold)
    Reason = CardHold.ReleaseReason
    now = timezone.now()
    if hold.status in CardHold.UNPLACED_STATUSES:
        if not _release_scheduled(hold.pk, Reason.CARD_RELEASED):
            return CaptureResult(CaptureStatus.IN_PROGRESS)
        return CaptureResult(CaptureStatus.NOTHING_DUE)
    if hold.status in CardHold.OPEN_STATUSES:
        outcome, detail = _release_for_charge(hold, Reason.CARD_RELEASED)
        if outcome == _ForCharge.CAPTURED:
            return _captured(detail, 0)
        if outcome == _ForCharge.RELEASED:
            return CaptureResult(CaptureStatus.NOTHING_DUE)
        return CaptureResult(CaptureStatus.NOT_CAPTURED, error=detail)
    if hold.status == CardHold.Status.FAILED:
        if hold.kept_at is None:
            logger.warning("Card hold %s failed and staff haven't kept it; not settled", hold.pk)
            return CaptureResult(CaptureStatus.NOT_CAPTURED)
        if not CardHold.objects.filter(
            pk=hold.pk, status=CardHold.Status.FAILED, charge_key=""
        ).update(
            status=CardHold.Status.RELEASED,
            release_reason=Reason.CARD_RELEASED,
            release_confirmed_at=now,
            modified=now,
        ):
            return CaptureResult(CaptureStatus.IN_PROGRESS)
        send_on_commit(card_hold_released, hold_id=hold.pk)
        return CaptureResult(CaptureStatus.NOTHING_DUE)
    if hold.release_reason in CardHold.BACK_TO_SCHEDULED_REASONS:
        if hold.release_confirmed_at is None or not CardHold.objects.filter(
            pk=hold.pk,
            status=CardHold.Status.RELEASED,
            release_reason=hold.release_reason,
            release_confirmed_at__isnull=False,
            charge_key="",
        ).update(release_reason=Reason.CARD_RELEASED, modified=now):
            return CaptureResult(CaptureStatus.IN_PROGRESS)
    return CaptureResult(CaptureStatus.NOTHING_DUE)


# --- Above the hold: the difference, payment status, fees and invoices ----------------

# Every payment's balance transaction, for Stripe's actual fee.
FEE_EXPAND = ["latest_charge.balance_transaction"]
# ``metadata['kind']`` of the difference PaymentIntent this module creates above a hold:
# reconciliation records it as the difference, never as a stray authorization.
DIFFERENCE_KIND = "difference"


def difference_idempotency_key(card_hold_id: int, generation: int = 0) -> str:
    """The key of the charge of the difference above a captured hold: one per hold and
    ``generation`` (``difference_generation``), bumped by each charge Stripe definitely
    refused, so a retry after a decline isn't Stripe replaying that decline."""
    return f"{key_prefix()}-difference-{card_hold_id}-{generation}"


def _fee_of(payment_intent: Any) -> tuple[int | None, str]:
    """Stripe's fee for a PaymentIntent's charge and its currency, from the expanded
    ``latest_charge.balance_transaction``; ``(None, "")`` when it isn't there (not
    expanded, or Stripe hasn't made the balance transaction yet)."""
    transaction_ = stripe_field(
        stripe_field(payment_intent, "latest_charge"), "balance_transaction"
    )
    fee = stripe_field(transaction_, "fee")
    if fee is None:
        return None, ""
    return int(fee), str(stripe_field(transaction_, "currency") or "")


def _store_fee(card_hold_id: int, field: str, payment_intent: Any) -> bool:
    """Record the fee of ``payment_intent`` in ``field`` if it is known and not recorded
    yet; whether it was."""
    fee, currency = _fee_of(payment_intent)
    if fee is None:
        return False
    changes: dict[str, Any] = {field: fee}
    if currency:
        changes["fee_currency"] = currency
    return bool(
        _holds().objects.filter(pk=card_hold_id, **{f"{field}__isnull": True}).update(**changes)
    )


def _is_difference(payment_intent: Any) -> bool:
    return stripe_field(stripe_field(payment_intent, "metadata"), "kind") == DIFFERENCE_KIND


def _difference_key_of(payment_intent: Any) -> str:
    return str(stripe_field(stripe_field(payment_intent, "metadata"), "difference_key") or "")


def _difference_params(hold: "AbstractCardHold") -> dict[str, Any]:
    """The difference's PaymentIntent: automatic capture, off-session, on the hold's card
    and customer, naming the hold (``card_hold_id``), the kind and the key it was sent
    with, so the webhook and the lookup recognise it."""
    return {
        "amount": hold.difference_amount_cents,
        "currency": hold.currency,
        "customer": hold.stripe_customer_id,
        "payment_method": hold.stripe_payment_method_id,
        "payment_method_types": ["card"],
        "confirm": True,
        "off_session": True,
        "metadata": {
            "card_hold_id": str(hold.pk),
            "kind": DIFFERENCE_KIND,
            "difference_key": hold.difference_key,
        },
        "expand": FEE_EXPAND,
    }


def _settle_difference(
    hold: "AbstractCardHold", amount_cents: int, *, check_target: bool = False
) -> CaptureResult:
    """A hold captured in full for an amount above it, under the capture claim: answer
    from the database, or charge the difference (claimed first, in a conditional UPDATE
    committed before Stripe is called).

    Asked for another amount than the one planned: the new ask is recorded and the
    difference isn't charged (:func:`_difference_not_asked`). Paid already (the
    difference charged, or staff marked it paid outside): ``paid``. A claim whose charge
    got no usable answer is resumed with its key. After a refusal (or with
    ``check_target``, the sweep's path), the claim is taken in the same transaction that
    re-checks the target under its lock and then the hold's: a cancelled (or deleted)
    target charges nothing (``partially_paid`` after a refusal; the sweep's path blocks
    it, :func:`_difference_target_cancelled`)."""
    CardHold = type(hold)
    captured = (
        hold.captured_amount_cents if hold.captured_amount_cents is not None else hold.amount_cents
    )
    if amount_cents != captured + hold.difference_amount_cents:
        return _difference_not_asked(hold, amount_cents)
    if hold.payment_status == CardHold.PaymentStatus.PAID:
        return CaptureResult(CaptureStatus.PAID)
    if hold.requested_amount_cents != amount_cents:
        # Asked for the planned amount again after another ask: it is the last one now.
        _open_plan(hold).update(requested_amount_cents=amount_cents, modified=timezone.now())
    if hold.difference_key:
        return _charge_difference(hold.pk)
    if check_target or hold.difference_generation:
        claimed = _claim_difference_if_target_alive(hold)
        if claimed is None:
            if check_target:
                return _difference_target_cancelled(hold)
            logger.warning(
                "Card hold %s: its target was cancelled after the difference was refused;"
                " not charging it",
                hold.pk,
            )
            return CaptureResult(CaptureStatus.PARTIALLY_PAID)
    else:
        claimed = _claim_difference(hold)
    if not claimed:
        return CaptureResult(CaptureStatus.IN_PROGRESS)
    return _charge_difference(hold.pk)


def _open_plan(hold: "AbstractCardHold") -> Any:
    """The hold's row while its planned difference is neither claimed nor charged, nor
    the target paid: what a new ask may still change."""
    CardHold = type(hold)
    return CardHold.objects.filter(
        pk=hold.pk,
        status=CardHold.Status.CAPTURED,
        difference_key="",
        difference_charged_at__isnull=True,
    ).exclude(payment_status=CardHold.PaymentStatus.PAID)


def _difference_not_asked(hold: "AbstractCardHold", amount_cents: int) -> CaptureResult:
    """Under the capture claim: the hold was captured in full for a difference planned on
    top, and now ``amount_cents``, another amount, is asked for. Nothing is charged.

    The new ask is recorded (``requested_amount_cents``, a conditional UPDATE, only while
    the difference is neither claimed nor charged), so neither a retry nor the sweep
    charges the old plan. Asked for exactly the amount captured, nothing more is due: the
    plan is dropped and the target is ``paid`` (``captured``). Asked for less, the
    customer was charged more than asked: ``not_captured``, logged as an error for a
    person (refunds are out of scope); any other amount likewise."""
    CardHold = type(hold)
    captured = hold.captured_amount_cents
    if captured is not None and amount_cents == captured:
        if _set_payment_status(
            hold.pk,
            CardHold.PaymentStatus.PAID,
            (CardHold.PaymentStatus.UNPAID, CardHold.PaymentStatus.PARTIALLY_PAID),
            q=Q(
                status=CardHold.Status.CAPTURED,
                difference_key="",
                difference_charged_at__isnull=True,
                captured_amount_cents=captured,
            ),
            requested_amount_cents=amount_cents,
            difference_amount_cents=None,
        ):
            logger.warning(
                "Card hold %s: asked for the %s captured, not %s; the difference of %s is"
                " no longer due",
                hold.pk,
                captured,
                captured + hold.difference_amount_cents,
                hold.difference_amount_cents,
            )
            return CaptureResult(CaptureStatus.CAPTURED)
    else:
        _open_plan(hold).update(requested_amount_cents=amount_cents, modified=timezone.now())
    logger.error(
        "Card hold %s was captured for %s with %s due on top, not the %s asked; the"
        " difference isn't charged and it isn't marked paid. Settle it by hand.",
        hold.pk,
        captured,
        hold.difference_amount_cents,
        amount_cents,
    )
    return CaptureResult(CaptureStatus.NOT_CAPTURED)


def _claim_difference(hold: "AbstractCardHold") -> bool:
    """Claim the difference's charge with the next key (a conditional UPDATE): only a
    captured, unpaid hold with no claim, still at the generation read."""
    CardHold = type(hold)
    now = timezone.now()
    return bool(
        CardHold.objects.filter(
            pk=hold.pk,
            status=CardHold.Status.CAPTURED,
            difference_key="",
            difference_generation=hold.difference_generation,
            difference_charged_at__isnull=True,
        )
        .exclude(payment_status=CardHold.PaymentStatus.PAID)
        .update(
            difference_key=difference_idempotency_key(hold.pk, hold.difference_generation),
            difference_claimed_at=now,
            modified=now,
        )
    )


def _claim_difference_if_target_alive(hold: "AbstractCardHold") -> bool | None:
    """Claim the difference (:func:`_claim_difference`) in the transaction that re-checks
    the target, so a cancellation can't commit between the check and the claim. ``None``
    for a cancelled (or deleted) target, else whether it was claimed. The claim commits
    when this returns, before any Stripe call."""
    return _under_live_target(hold, lambda: _claim_difference(hold))


def _difference_target_alive(hold: "AbstractCardHold") -> bool:
    """Whether the hold's target is still there and not cancelled (under its lock, then
    the hold's). No Stripe call."""
    return _under_live_target(hold, lambda: True) is not None


def _under_live_target(hold: "AbstractCardHold", then: Callable[[], bool]) -> bool | None:
    """In one transaction, lock the hold's target, then the hold (that order, as
    everywhere): ``None`` when the target is gone or cancelled, else what ``then``
    returns, run under both locks. No Stripe call."""
    adapter = registered[1] if (registered := _registered(hold)) is not None else None
    if adapter is None:
        return None
    with transaction.atomic():
        target = adapter.lock(hold.target_document.object_id)
        type(hold).objects.select_for_update().filter(pk=hold.pk).first()
        if _why_not_holdable(adapter, target) == type(hold).ReleaseReason.CANCELLED:
            return None
        return then()


def _difference_target_cancelled(hold: "AbstractCardHold") -> CaptureResult:
    """The sweep found the target of a hold with its difference still due cancelled (or
    deleted): nothing is charged, and the row is marked (``charge_blocked_reason``
    ``target_cancelled``) so the sweep stops queuing it; logged once, for a person to
    decide. A ``capture()`` still charges it if the project asks."""
    CardHold = type(hold)
    if _block_charge(hold.pk, CardHold.ChargeBlock.TARGET_CANCELLED):
        logger.error(
            "Card hold %s: its target was cancelled (or deleted) with the difference of %s"
            " still due; not charging it. Decide by hand.",
            hold.pk,
            hold.difference_amount_cents,
        )
    return CaptureResult(CaptureStatus.NOT_CAPTURED)


def _charge_difference(card_hold_id: int) -> CaptureResult:
    """Charge the claimed difference (``difference_key``) off-session, once.

    Stripe's answer decides: ``succeeded`` is ``paid`` (recorded with the PaymentIntent
    and its fee); a definite refusal (a ``CardError``, a non-409 ``InvalidRequestError``,
    or a PaymentIntent left needing a payment method) is ``partially_paid``: the claim is
    dropped and the generation bumped, so the next call sends a new key. No usable answer
    (a connection error, a 5xx, a 429, a 409, a bad key, ``IdempotencyError``) propagates
    and keeps the claim: the next call replays it with the same key. A claim older than
    :data:`CHARGE_KEY_TTL` is never replayed (Stripe may have forgotten the key): it is
    reconciled from Stripe instead (:func:`_reconcile_difference`). One Stripe answered
    ``processing`` (its PaymentIntent recorded) is read back from Stripe, not replayed.
    With no claim, a refusal recorded meanwhile answers ``partially_paid``."""
    CardHold = _holds()
    hold = CardHold.objects.get(pk=card_hold_id)
    if hold.difference_charged_at is not None or hold.payment_status == CardHold.PaymentStatus.PAID:
        return CaptureResult(CaptureStatus.PAID)
    key = hold.difference_key
    if not key:
        if hold.payment_status == CardHold.PaymentStatus.PARTIALLY_PAID:
            return CaptureResult(CaptureStatus.PARTIALLY_PAID)
        return CaptureResult(CaptureStatus.NOT_CAPTURED)
    if hold.difference_payment_intent_id:
        intent = utils.get_stripe().PaymentIntent.retrieve(
            hold.difference_payment_intent_id, expand=FEE_EXPAND
        )
        return _difference_outcome(hold.pk, key, intent)
    if hold.difference_claimed_at is None or hold.difference_claimed_at < (
        timezone.now() - CHARGE_KEY_TTL
    ):
        return _reconcile_difference(hold)
    try:
        intent = utils.get_stripe().PaymentIntent.create(
            **_difference_params(hold), idempotency_key=key
        )
    except stripe.IdempotencyError:
        logger.error(
            "Card hold %s: Stripe refused the difference key %s as reused with other"
            " parameters; the first charge with it may have run. Check Stripe.",
            hold.pk,
            key,
        )
        raise
    except (stripe.CardError, stripe.InvalidRequestError) as error:
        if getattr(error, "http_status", None) == 409:
            raise
        _difference_refused(hold.pk, key, _placement_failure(None, error) or "card_declined")
        return CaptureResult(CaptureStatus.PARTIALLY_PAID, error=error)
    return _difference_outcome(hold.pk, key, intent)


def _difference_outcome(card_hold_id: int, key: str, intent: Any) -> CaptureResult:
    """Record what the difference's PaymentIntent ended in."""
    status = stripe_field(intent, "status")
    if status == "succeeded":
        _record_difference(card_hold_id, key, intent)
        return CaptureResult(CaptureStatus.PAID, payment_intent=intent)
    if status == "processing":
        # Not decided yet: the claim stays, and the webhook records the outcome. Its id is
        # kept, so the next call reads it back instead of replaying the create.
        _holds().objects.filter(
            pk=card_hold_id, difference_key=key, difference_charged_at__isnull=True
        ).update(difference_payment_intent_id=stripe_id(intent))
        return CaptureResult(CaptureStatus.IN_PROGRESS, payment_intent=intent)
    _difference_refused(card_hold_id, key, _placement_failure(intent, None) or str(status))
    return CaptureResult(CaptureStatus.PARTIALLY_PAID, payment_intent=intent)


def _record_difference(card_hold_id: int, key: str, intent: Any) -> bool:
    """The difference claimed with ``key`` was charged: record its PaymentIntent, when,
    and its fee (when known), and the target is ``paid``. Whether this call recorded it
    (a webhook and the call itself may both try; one does)."""
    CardHold = _holds()
    now = timezone.now()
    changes: dict[str, Any] = {
        "difference_payment_intent_id": stripe_id(intent),
        "difference_charged_at": now,
        "difference_failure_code": "",
        "modified": now,
    }
    fee, currency = _fee_of(intent)
    if fee is not None:
        changes["difference_fee_cents"] = fee
        if currency:
            changes["fee_currency"] = currency
    if not CardHold.objects.filter(
        pk=card_hold_id, difference_key=key, difference_charged_at__isnull=True
    ).update(**changes):
        return False
    _set_payment_status(
        card_hold_id,
        CardHold.PaymentStatus.PAID,
        (CardHold.PaymentStatus.UNPAID, CardHold.PaymentStatus.PARTIALLY_PAID),
    )
    return True


def _difference_refused(card_hold_id: int, key: str, code: str) -> bool:
    """Stripe definitely refused the difference claimed with ``key``: nothing was taken
    for it. The claim is dropped and ``difference_generation`` bumped in one statement;
    the target is ``partially_paid`` (the hold's capture stays), and
    ``difference_charge_failed`` is sent once for this refusal. Whether this call
    recorded it."""
    CardHold = _holds()
    if not CardHold.objects.filter(
        pk=card_hold_id, difference_key=key, difference_charged_at__isnull=True
    ).update(
        difference_key="",
        difference_claimed_at=None,
        difference_payment_intent_id=None,
        difference_generation=F("difference_generation") + 1,
        difference_failure_code=code[:64],
        modified=timezone.now(),
    ):
        return False
    logger.warning(
        "Card hold %s: the difference charged with key %s was refused (%s)",
        card_hold_id,
        key,
        code,
    )
    _set_payment_status(
        card_hold_id, CardHold.PaymentStatus.PARTIALLY_PAID, (CardHold.PaymentStatus.UNPAID,)
    )
    hold = CardHold.objects.select_related("target_document").get(pk=card_hold_id)
    send_on_commit(
        difference_charge_failed,
        hold=hold,
        target=hold.target,
        amount_due_cents=hold.difference_amount_cents,
        error_code=code,
    )
    return True


def _reconcile_difference(hold: "AbstractCardHold") -> CaptureResult:
    """A difference claimed more than :data:`CHARGE_KEY_TTL` ago with no recorded answer:
    never replayed blind. Its PaymentIntents (``kind`` difference, the claim's key) are
    looked up in Stripe (:func:`find_difference_payment_intents`, never the project's
    ``BASEAPP_PAYMENTS_CARD_HOLD_LOOKUP``, written for authorizations) and the outcome
    recorded; with none found the request never ran, so the key is rotated and the
    difference charged afresh with the next one."""
    key = hold.difference_key
    try:
        found = find_difference_payment_intents(hold)
    except stripe.StripeError:
        logger.warning("Could not look up card hold %s's difference", hold.pk, exc_info=True)
        return CaptureResult(CaptureStatus.IN_PROGRESS)
    statuses = [stripe_field(pi, "status") for pi in found]
    if "succeeded" in statuses:
        intent = found[statuses.index("succeeded")]
        _record_difference(hold.pk, key, intent)
        return CaptureResult(CaptureStatus.PAID, payment_intent=intent)
    if "processing" in statuses:
        return CaptureResult(CaptureStatus.IN_PROGRESS)
    if found:
        return _difference_outcome(hold.pk, key, found[0])
    logger.warning(
        "Card hold %s: nothing in Stripe answers difference %s; charging it afresh", hold.pk, key
    )
    CardHold = type(hold)
    if not CardHold.objects.filter(
        pk=hold.pk, difference_key=key, difference_charged_at__isnull=True
    ).update(
        difference_key="",
        difference_claimed_at=None,
        difference_generation=F("difference_generation") + 1,
        modified=timezone.now(),
    ):
        return CaptureResult(CaptureStatus.IN_PROGRESS)
    hold.refresh_from_db()
    if not _claim_difference(hold):
        return CaptureResult(CaptureStatus.IN_PROGRESS)
    return _charge_difference(hold.pk)


def _apply_difference(hold: "AbstractCardHold", payment_intent: Any) -> str:
    """Under the hold's lock (:func:`_apply_payment_intent`): record what Stripe says of
    a difference PaymentIntent naming this hold. Only the outstanding claim's own
    (``difference_key``) is recorded: ``recorded`` when it succeeded, ``declined`` when it
    was refused; ``current`` for the one already recorded. It is a payment, not an
    authorization, so it is never cancelled as a stray."""
    payment_intent_id = stripe_id(payment_intent)
    status = stripe_field(payment_intent, "status")
    if hold.difference_charged_at is not None:
        if hold.difference_payment_intent_id == payment_intent_id:
            return "current"
        if status == "succeeded":
            logger.error(
                "Card hold %s: difference PaymentIntent %s succeeded but %s was recorded;"
                " check Stripe",
                hold.pk,
                payment_intent_id,
                hold.difference_payment_intent_id,
            )
        return "ignored"
    key = _difference_key_of(payment_intent)
    if not key or key != hold.difference_key:
        return "ignored"
    if status == "succeeded":
        _record_difference(hold.pk, key, payment_intent)
        return "recorded"
    if status in ("requires_payment_method", "canceled"):
        _difference_refused(hold.pk, key, _placement_failure(payment_intent, None) or status)
        return "declined"
    return "ignored"


def _difference_due(hold: "AbstractCardHold") -> int | None:
    """The final amount of a captured hold whose difference is still due and was never
    refused: the amount captured plus the difference, when that is what the last
    :func:`capture` asked for (or nothing was recorded); else ``None``."""
    CardHold = type(hold)
    if (
        hold.status != CardHold.Status.CAPTURED
        or hold.difference_amount_cents is None
        or hold.difference_charged_at is not None
        or hold.payment_status != CardHold.PaymentStatus.UNPAID
        or hold.captured_amount_cents is None
        or hold.charge_blocked_reason
    ):
        return None
    amount = hold.captured_amount_cents + hold.difference_amount_cents
    if hold.requested_amount_cents is not None and hold.requested_amount_cents != amount:
        return None
    return amount


def charge_due_difference(card_hold_id: int) -> CaptureResult:
    """Re-drive the difference of a hold captured in full whose :func:`capture` never came
    back for it (the caller stopped retrying): queued by the sweep. Under the capture
    claim, through the same claimed, keyed path as :func:`capture` (a claim whose charge
    got no answer is resumed with its key, or reconciled past :data:`CHARGE_KEY_TTL`).

    Only a difference still due and never refused (``unpaid``: a refused one waits for
    the project), for the amount the last :func:`capture` asked. The target is checked
    under its lock and then the hold's, in the transaction that claims the difference: a
    cancelled (or deleted) one is not charged, and the row is marked
    (``charge_blocked_reason`` ``target_cancelled``) and logged once, for someone to
    decide; the sweep then leaves it. ``in_progress`` while a capture holds the claim,
    ``not_captured`` when nothing is due. Stripe's errors propagate. Raises
    :class:`CardHoldInTransaction` inside a transaction."""
    _ensure_outside_transaction()
    claimed_at = _claim_capture(card_hold_id)
    if claimed_at is None:
        return CaptureResult(CaptureStatus.IN_PROGRESS)
    try:
        hold = _seen(card_hold_id)
        amount_cents = _difference_due(hold) if hold is not None else None
        if amount_cents is None:
            return CaptureResult(CaptureStatus.NOT_CAPTURED)
        if hold.difference_key and not _difference_target_alive(hold):
            return _difference_target_cancelled(hold)
        return _settle_difference(hold, amount_cents, check_target=True)
    finally:
        _release_capture_claim(card_hold_id, claimed_at)


def mark_paid_outside(card_hold_id: int, actor: "AbstractBaseUser | None" = None) -> bool:
    """Staff record the rest of a ``partially_paid`` target as paid outside the app: it
    moves to ``paid`` (``paid_outside_at`` / ``paid_outside_by``), and no later
    :func:`capture` charges the difference. One conditional UPDATE, refused while a
    capture holds the claim (or a difference charge is claimed); no Stripe call. Whether
    it was marked."""
    CardHold = _holds()
    now = timezone.now()
    return _set_payment_status(
        card_hold_id,
        CardHold.PaymentStatus.PAID,
        (CardHold.PaymentStatus.PARTIALLY_PAID,),
        q=Q(difference_key="", difference_charged_at__isnull=True)
        & (
            Q(capture_claimed_at__isnull=True)
            | Q(capture_claimed_at__lt=now - CAPTURE_CLAIM_TIMEOUT)
        ),
        paid_outside_at=now,
        paid_outside_by=actor if getattr(actor, "is_authenticated", False) else None,
    )


def hold_payment_intent_ids(hold: "AbstractCardHold") -> list[str]:
    """Every PaymentIntent that took money for ``hold``'s target, oldest first: the
    hold's capture, the difference above it, or the single full charge (when the
    project's ``charge`` returned it). From the row; no query."""
    CardHold = type(hold)
    found = []
    if hold.status == CardHold.Status.CAPTURED and hold.stripe_payment_intent_id:
        found.append(hold.stripe_payment_intent_id)
    if hold.difference_charged_at is not None and hold.difference_payment_intent_id:
        found.append(hold.difference_payment_intent_id)
    if hold.charged_at is not None and hold.charge_payment_intent_id:
        found.append(hold.charge_payment_intent_id)
    return found


def attach_payments_to_invoice(card_hold_id: int, invoice_id: str) -> list[str]:
    """Record every payment of a hold's target on the project's Stripe invoice for it:
    each PaymentIntent (:func:`hold_payment_intent_ids`) not attached yet is attached
    with ``Invoice.attach_payment`` (API 2025-03-31.basil and later; a succeeded one is
    credited at once). Returns the PaymentIntent ids now on the invoice from this hold.

    The invoice must be finalized (``open``), for the hold's customer and currency, and
    its ``amount_remaining`` must cover them: create it with ``collection_method=
    "send_invoice"`` and ``auto_advance=False``, so Stripe doesn't also try to collect it.
    Each attach has its own idempotency key, and PaymentIntents already on the invoice
    (every page of ``InvoicePayment.list(invoice=...)``) are skipped, so calling it again
    is safe. Stripe's errors
    propagate. Raises :class:`CardHoldInTransaction` inside a transaction."""
    _ensure_outside_transaction()
    hold = _holds().objects.get(pk=card_hold_id)
    payment_intent_ids = hold_payment_intent_ids(hold)
    if not payment_intent_ids:
        return []
    stripe_api = utils.get_stripe()
    # Every page: the invoice's own ``payments`` holds only the first handful.
    listed = stripe_api.InvoicePayment.list(invoice=invoice_id, limit=100)
    attached = {
        stripe_id(stripe_field(stripe_field(payment, "payment"), "payment_intent"))
        for payment in listed.auto_paging_iter()
    }
    for payment_intent_id in payment_intent_ids:
        if payment_intent_id in attached:
            continue
        stripe_api.Invoice.attach_payment(
            invoice_id,
            payment_intent=payment_intent_id,
            idempotency_key=f"{key_prefix()}-invoice-{invoice_id}-{payment_intent_id}",
        )
    return payment_intent_ids


def record_fees(card_hold_id: int) -> int:
    """Read Stripe's fee for each payment of the hold whose fee isn't recorded yet (its
    balance transaction wasn't ready when it was taken), from the PaymentIntent's
    ``latest_charge.balance_transaction``. No lock held; Stripe's transient errors
    propagate. Returns how many fees it recorded (the sweep queues it again for the
    rest)."""
    hold = _holds().objects.filter(pk=card_hold_id).first()
    if hold is None:
        return 0
    due = []
    if hold.status == type(hold).Status.CAPTURED and hold.capture_fee_cents is None:
        due.append(("capture_fee_cents", hold.stripe_payment_intent_id))
    if hold.difference_charged_at is not None and hold.difference_fee_cents is None:
        due.append(("difference_fee_cents", hold.difference_payment_intent_id))
    if hold.charged_at is not None and hold.charge_fee_cents is None:
        due.append(("charge_fee_cents", hold.charge_payment_intent_id))
    recorded = 0
    for field, payment_intent_id in due:
        if not payment_intent_id:
            continue
        try:
            intent = utils.get_stripe().PaymentIntent.retrieve(payment_intent_id, expand=FEE_EXPAND)
        except stripe.InvalidRequestError:
            logger.warning("Could not read PaymentIntent %s", payment_intent_id, exc_info=True)
            continue
        recorded += _store_fee(hold.pk, field, intent)
    return recorded


# --- Deferred placement -----------------------------------------------------------------


def scheduled_idempotency_key(hold: "AbstractCardHold") -> str:
    """The key of one scheduled placement of ``hold``: stable across retries of it, new
    for each attempt (re-arming gives a new one), each authorization the row held
    before (rescheduling a placed hold moves it to ``previous_payment_intent_ids``) and
    each placement reconciled with nothing found in Stripe (``placement_generation``)."""
    generation = len(hold.previous_payment_intent_ids or [])
    key = f"{key_prefix()}-hold-scheduled-{hold.pk}-{hold.attempt_id}-{generation}"
    return f"{key}-{hold.placement_generation}" if hold.placement_generation else key


def _card_of_hold(hold: "AbstractCardHold") -> Card:
    return Card(
        payment_method_id=hold.stripe_payment_method_id,
        brand=hold.card_brand,
        last4=hold.card_last4,
        exp_month=hold.card_exp_month,
        exp_year=hold.card_exp_year,
        funding=hold.card_funding,
        fingerprint=hold.card_fingerprint,
    )


def _registered(hold: "AbstractCardHold") -> tuple[type[Model], HoldTarget] | None:
    """The target model and adapter of a linked hold, or ``None`` (unlinked, or its
    target model is no longer registered)."""
    if hold.target_document_id is None:
        return None
    registered = target_for_content_type_id(hold.target_document.content_type_id)
    if registered is None:
        logger.error("Card hold %s backs an unregistered target", hold.pk)
    return registered


def _seen(card_hold_id: int, **filters: Any) -> "AbstractCardHold | None":
    """The hold, read without a lock, with its target document."""
    return (
        _holds()
        .objects.filter(pk=card_hold_id, **filters)
        .select_related("target_document")
        .first()
    )


def _lock_target_and_hold(
    seen: "AbstractCardHold", adapter: HoldTarget | None, **filters: Any
) -> tuple[Model | None, "AbstractCardHold | None"]:
    """Inside a transaction: lock ``seen``'s target (``None`` when gone), then the hold
    (``None`` when it no longer matches ``filters`` or changed target meanwhile)."""
    target = None
    if adapter is not None:
        target = adapter.lock(seen.target_document.object_id)
    hold = _holds().objects.select_for_update().filter(pk=seen.pk, **filters).first()
    if hold is not None and hold.target_document_id != seen.target_document_id:
        return target, None
    return target, hold


def _why_not_holdable(adapter: HoldTarget, target: Model | None) -> str | None:
    """The ``ReleaseReason`` for a target that must not get its hold any more (gone or
    cancelled, done with the card), ``""`` for one that just isn't holdable now
    (``filter_holdable``), ``None`` for one that is."""
    Reason = _holds().ReleaseReason
    if target is None or is_cancelled(adapter, target.pk):
        return Reason.CANCELLED
    if is_card_released(adapter, target.pk):
        return Reason.CARD_RELEASED
    one = adapter.model._default_manager.filter(pk=target.pk)
    if not adapter.filter_holdable(one).exists():
        return ""
    return None


@dataclass
class _PlacementClaim:
    hold: "AbstractCardHold"
    # None: the hold's target was deleted while its placement was unsettled.
    adapter: HoldTarget | None
    claimed_at: datetime.datetime


_CLEARED_PLACEMENT = {
    "placement_key": "",
    "placement_amount_cents": None,
    "placement_sent_at": None,
}


def _claim_placement(card_hold_id: int) -> "_PlacementClaim | PlacementResult | None":
    """Under the target's lock, then the hold's, claim a scheduled hold for one
    off-session placement (committed before Stripe is called).

    A placement already claimed by a live call answers ``in_progress``. A first claim
    (nothing while ``CARD_HOLDS_DEFERRAL_ENABLED`` is off) re-checks the target (gone or
    cancelled, or done with the card: released here with no Stripe call; outside
    ``filter_holdable``: left scheduled), checks the day has come, prices the target
    now, and records the idempotency key and amount. A claim of a placement whose earlier
    create had no usable answer (``placement_key`` set) keeps that key and amount
    whatever the target's state or the setting, so Stripe replays or settles it; that
    includes a hold whose target was deleted since (unlinked), whose replayed
    authorization is then cancelled.
    """
    CardHold = _holds()
    seen = _seen(card_hold_id, status=CardHold.Status.SCHEDULED)
    if seen is None:
        return None
    adapter = None
    if seen.target_document_id is not None:
        registered = _registered(seen)
        if registered is None:
            return None
        adapter = registered[1]
    elif not seen.placement_key:
        return None
    now = timezone.now()
    with transaction.atomic():
        target, hold = _lock_target_and_hold(seen, adapter, status=CardHold.Status.SCHEDULED)
        if hold is None:
            return None
        if hold.placement_claimed_at and hold.placement_claimed_at > now - PLACEMENT_CLAIM_TIMEOUT:
            return PlacementResult(PlacementStatus.IN_PROGRESS, target=target, hold=hold)
        fields = ["placement_claimed_at", "modified"]
        if not hold.placement_key:
            if adapter is None or not deferral_enabled():
                return None
            reason = _why_not_holdable(adapter, target)
            if reason:
                _release_scheduled(hold.pk, reason)
                return PlacementResult(PlacementStatus.REFUSED, target=target, hold=hold)
            if reason is not None:
                return PlacementResult(PlacementStatus.REFUSED, target=target, hold=hold)
            if hold.hold_on is not None and hold.hold_on > _today():
                return PlacementResult(PlacementStatus.SCHEDULED, target=target, hold=hold)
            estimated, buffer, amount = price(adapter, target, _card_of_hold(hold))
            if amount <= 0:
                _fail(hold, target, adapter, "nothing_to_hold")
                return PlacementResult(PlacementStatus.DECLINED, target=target, hold=hold)
            hold.estimated_amount_cents = estimated
            hold.buffer_percent = buffer
            hold.amount_cents = amount
            hold.placement_key = scheduled_idempotency_key(hold)
            hold.placement_amount_cents = amount
            hold.placement_sent_at = now
            fields += [
                "estimated_amount_cents",
                "buffer_percent",
                "amount_cents",
                "placement_key",
                "placement_amount_cents",
                "placement_sent_at",
            ]
        elif hold.placement_sent_at is None:
            # A key on record with no first send: counted from now, never left unbounded.
            hold.placement_sent_at = now
            fields.append("placement_sent_at")
        hold.placement_claimed_at = now
        hold.save(update_fields=fields)
    return _PlacementClaim(hold=hold, adapter=adapter, claimed_at=now)


def _create_off_session(hold: "AbstractCardHold") -> tuple[Any, Exception | None]:
    """The off-session, manual-capture PaymentIntent of a claimed scheduled hold, with
    its claimed key and amount: ``(payment_intent, None)`` or ``(None, error)``. A
    replay is re-read, so its live state is what's settled."""
    try:
        payment_intent = utils.get_stripe().PaymentIntent.create(
            amount=hold.placement_amount_cents,
            currency=hold.currency,
            customer=hold.stripe_customer_id,
            payment_method=hold.stripe_payment_method_id,
            payment_method_types=["card"],
            capture_method="manual",
            confirm=True,
            off_session=True,
            metadata={
                "user_id": str(hold.customer_id),
                "attempt_id": str(hold.attempt_id),
                "card_hold_id": str(hold.pk),
            },
            expand=PAYMENT_INTENT_EXPAND,
            idempotency_key=hold.placement_key,
        )
        if is_idempotent_replay(payment_intent):
            payment_intent = retrieve_payment_intent(stripe_id(payment_intent))
    except stripe.StripeError as error:
        return None, error
    return payment_intent, None


# Stripe's answers about the request itself: a decline, a refusal of its parameters, a
# key reused with others. Anything else says nothing about the card.
_DEFINITE_STRIPE_ERRORS = (stripe.CardError, stripe.InvalidRequestError, stripe.IdempotencyError)


def _placement_failure(payment_intent: Any, error: Exception | None) -> str | None:
    """Why an off-session placement failed for good (the hold's ``failure_code``), or
    ``None``: it succeeded, or had no usable answer, which is retried with the same key.

    Only a decline, a refusal of the request (``InvalidRequestError``) or a reused key
    fails the hold. A connection error, a 5xx, a 429, a 409, a bad or revoked API key
    (``AuthenticationError``, ``PermissionError``) or any other Stripe error is no
    usable answer: the hold stays scheduled and no staff are told."""
    if error is not None:
        if getattr(error, "http_status", None) == 409 or not isinstance(
            error, _DEFINITE_STRIPE_ERRORS
        ):
            return None
        if isinstance(error, stripe.CardError):
            detail = getattr(error, "error", None)
            return (
                stripe_field(detail, "decline_code")
                or getattr(error, "code", None)
                or "card_declined"
            )
        return getattr(error, "code", None) or type(error).__name__
    status = stripe_field(payment_intent, "status")
    if status in ("requires_capture", "processing"):
        return None
    if status == "requires_action":
        return "authentication_required"
    if status == "requires_payment_method":
        declined = stripe_field(payment_intent, "last_payment_error")
        return stripe_field(declined, "decline_code") or stripe_field(declined, "code") or status
    return status or "unknown"


def _fail(
    hold: "AbstractCardHold",
    target: Model,
    adapter: HoldTarget,
    code: str,
    payment_intent_id: str | None = None,
) -> None:
    """Mark a locked scheduled hold ``failed`` (final), and once that commits send
    ``card_hold_failed`` and let the adapter tell staff. The customer isn't told."""
    CardHold = type(hold)
    hold.status = CardHold.Status.FAILED
    hold.failed_at = timezone.now()
    hold.failure_code = code[:64]
    hold.placement_claimed_at = None
    if payment_intent_id and hold.stripe_payment_intent_id is None:
        hold.stripe_payment_intent_id = payment_intent_id
    hold.save()
    logger.warning("Card hold %s failed off-session: %s", hold.pk, code)
    send_on_commit(card_hold_failed, hold=hold, target=target)
    transaction.on_commit(lambda: adapter.notify_hold_failed(target, hold), robust=True)


def _settle_placement(
    claim: _PlacementClaim, payment_intent: Any, error: Exception | None
) -> PlacementResult:
    """Record what the off-session create ended in, under the target's lock, then the
    hold's: ``authorized`` (``placed``); ``failed`` (``declined``, final, staff told);
    or, with no usable answer, still ``scheduled`` with its key, for the next sweep to
    retry (``in_progress``). A target that may no longer take the hold has its new
    authorization released (and a refusal recorded without telling staff)."""
    CardHold = _holds()
    payment_intent_id = stripe_id(payment_intent) if payment_intent is not None else None
    if payment_intent_id is None and error is not None:
        payment_intent_id = stripe_id(stripe_field(getattr(error, "error", None), "payment_intent"))
    failure = _placement_failure(payment_intent, error)
    succeeded = failure is None and error is None and payment_intent is not None
    succeeded = succeeded and stripe_field(payment_intent, "status") == "requires_capture"
    seen = claim.hold
    with transaction.atomic():
        target, hold = _lock_target_and_hold(
            seen,
            claim.adapter,
            status=CardHold.Status.SCHEDULED,
            placement_key=seen.placement_key,
        )
        if hold is None:
            # The hold moved on: another call took the claim over (this one outlived its
            # timeout) and replays the same key, or a webhook or lookup settled it.
            _drop_overtaken(seen.pk, payment_intent, error)
            return PlacementResult(PlacementStatus.IN_PROGRESS)
        if not succeeded and failure is None:
            if hold.placement_claimed_at == claim.claimed_at:
                hold.placement_claimed_at = None
                hold.save(update_fields=["placement_claimed_at", "modified"])
            # A bad or revoked key stops every placement until someone fixes it.
            log = logger.error if isinstance(error, CONFIGURATION_STRIPE_ERRORS) else logger.warning
            log(
                "No usable answer placing card hold %s off-session; the sweep retries",
                hold.pk,
                exc_info=error,
            )
            return PlacementResult(PlacementStatus.IN_PROGRESS, target=target, hold=hold)
        return _settle_locked(
            hold, target, claim.adapter, payment_intent, payment_intent_id, failure
        )


def _drop_overtaken(card_hold_id: int, payment_intent: Any, error: Exception | None) -> None:
    """Inside :func:`_settle_placement`'s transaction, the target already locked: a
    placement whose hold moved on before its answer was recorded. Its own PaymentIntent,
    when it isn't one the hold carries or carried (a webhook or lookup settled the hold
    with another) and may still authorize, is tracked as a stray, so it is cancelled after the
    commit and re-driven by the sweep instead of being dropped."""
    if payment_intent is None and error is not None:
        payment_intent = stripe_field(getattr(error, "error", None), "payment_intent")
    payment_intent_id = stripe_id(payment_intent) if payment_intent is not None else None
    if not payment_intent_id or stripe_field(payment_intent, "status") not in (
        _CANCELLABLE_STATUSES
    ):
        return
    hold = _holds().objects.select_for_update().filter(pk=card_hold_id).first()
    if (
        hold is None
        or payment_intent_id == hold.stripe_payment_intent_id
        or payment_intent_id in (hold.stray_payment_intent_ids or [])
        or payment_intent_id in (hold.previous_payment_intent_ids or [])
    ):
        return
    _track_stray(hold, payment_intent_id)


def _settle_locked(
    hold: "AbstractCardHold",
    target: Model | None,
    adapter: HoldTarget | None,
    payment_intent: Any,
    payment_intent_id: str | None,
    failure: str | None,
) -> PlacementResult:
    """Record the definite outcome of a scheduled hold's placement, under the target's
    lock and then the hold's: an authorization (``failure`` ``None``) or a refusal. Shared
    by the placement's own answer and by reconciliation (a webhook, a lookup)."""
    CardHold = type(hold)
    succeeded = failure is None
    reason = _why_not_holdable(adapter, target)
    if succeeded and reason is None:
        hold.stripe_payment_intent_id = payment_intent_id
        hold.status = CardHold.Status.AUTHORIZED
        hold.amount_cents = stripe_field(payment_intent, "amount") or hold.amount_cents
        hold.expires_at = hold_expiry(payment_intent, OFF_SESSION_HOLD_EXPIRY_FALLBACK)
        hold.placement_claimed_at = None
        for field, value in _CLEARED_PLACEMENT.items():
            setattr(hold, field, value)
        hold.save()
        send_on_commit(card_hold_authorized, hold=hold, target=target)
        return PlacementResult(PlacementStatus.PLACED, target=target, hold=hold)
    if succeeded:
        _release_new_authorization(hold, payment_intent, reason)
        return PlacementResult(PlacementStatus.REFUSED, target=target, hold=hold)
    if reason:
        # Refused, but the target can't take a hold any more anyway: nobody to tell.
        hold.placement_claimed_at = None
        for field, value in _CLEARED_PLACEMENT.items():
            setattr(hold, field, value)
        hold.save()
        _release_scheduled(hold.pk, reason)
        if payment_intent_id:
            transaction.on_commit(
                lambda: cancel_payment_intent_quietly(payment_intent_id), robust=True
            )
        return PlacementResult(PlacementStatus.REFUSED, target=target, hold=hold)
    _fail(hold, target, adapter, failure, payment_intent_id)
    if payment_intent_id and stripe_field(payment_intent, "status") == "requires_action":
        # Nothing is held on it; cancelled so it doesn't linger in Stripe.
        transaction.on_commit(lambda: cancel_payment_intent_quietly(payment_intent_id), robust=True)
    return PlacementResult(PlacementStatus.DECLINED, target=target, hold=hold)


def _release_new_authorization(hold: "AbstractCardHold", payment_intent: Any, reason: str) -> None:
    """A placement authorized for a target that may no longer take it (a retried
    create settled after the target was cancelled, say). The hold is released with the
    new PaymentIntent and its expiry on it, unconfirmed, and the release task cancels
    it; until Stripe confirms the cancel, the sweep re-drives it and :func:`capture`
    never charges (the authorization may still be live).

    A target that must not get its hold any more is released for ``reason``. One only
    outside ``filter_holdable`` is released ``not_holdable``: once the cancel is
    confirmed it goes back to ``scheduled`` (:func:`_back_to_scheduled`, by
    :func:`reschedule_hold` or the sweep), as a rescheduled hold does."""
    CardHold = type(hold)
    payment_intent_id = stripe_id(payment_intent)
    hold.placement_claimed_at = None
    for field, value in _CLEARED_PLACEMENT.items():
        setattr(hold, field, value)
    hold.stripe_payment_intent_id = payment_intent_id
    hold.expires_at = hold_expiry(payment_intent, OFF_SESSION_HOLD_EXPIRY_FALLBACK)
    hold.status = CardHold.Status.RELEASED
    hold.release_reason = reason or CardHold.ReleaseReason.NOT_HOLDABLE
    hold.release_confirmed_at = None
    hold.save()
    send_on_commit(card_hold_released, hold_id=hold.pk)
    release_on_commit(hold.pk, claimed=True, payment_intent_id=payment_intent_id)


def place_scheduled(card_hold_id: int) -> PlacementResult | None:
    """Place a scheduled hold off-session, once its day has come (the sweep's job).

    The hold is claimed first, under the target's lock and then its own, and the claim
    commits before Stripe is called, so overlapping sweeps or a redelivered task place
    it once: a concurrent call answers ``in_progress`` and calls nothing. Stripe gets
    one off-session, manual-capture PaymentIntent for the target's current hold amount
    (estimate plus buffer), with :func:`scheduled_idempotency_key`.

    - ``placed``: authorized, with the expiry read from ``capture_before``;
    - ``declined``: refused for good (a decline, ``authentication_required``, any
      non-retryable Stripe error). The hold is ``failed`` with its ``failure_code``,
      ``card_hold_failed`` is sent and the adapter's ``notify_hold_failed`` tells staff.
      Never retried, and the customer isn't told;
    - ``in_progress``: no usable answer (a connection error, 5xx, 429, 409); the hold
      stays scheduled with its key, and the next sweep retries it, so Stripe replays any
      authorization it made. Only for :data:`PLACEMENT_KEY_TTL` after the key was first
      sent: past it, the placement is reconciled (:func:`_reconcile_placement`) instead;
    - ``refused``: the target can't take its hold (released, with no Stripe call, when
      it is cancelled or done with the card); ``scheduled``: its day hasn't come.

    ``None`` when there is nothing to place. Raises :class:`CardHoldInTransaction`
    inside a transaction.
    """
    _ensure_outside_transaction()
    if not utils.stripe_configured():
        return None
    claim = _claim_placement(card_hold_id)
    if not isinstance(claim, _PlacementClaim):
        return claim
    if _send_is_stale(claim.hold):
        return _reconcile_placement(claim)
    payment_intent, error = _create_off_session(claim.hold)
    return _settle_placement(claim, payment_intent, error)


# --- Reconciliation ---------------------------------------------------------------------
#
# A create with no usable answer (a 5xx, a connection error) may hide an authorization
# Stripe made. Replaying its key settles it, but only while Stripe keeps the key (24 hours
# at least). Past that a replay runs as a fresh request. So authorizations are matched to
# their row by ``metadata['card_hold_id']`` instead: from Stripe's webhooks (primary,
# :func:`reconcile_payment_intent`), and by a lookup once the key is
# :data:`PLACEMENT_KEY_TTL` old (:func:`_reconcile_placement`, :func:`reconcile_stale_send`).

# Statuses of a PaymentIntent that may still authorize, or holds, money: cancelled when
# they turn up on a hold that doesn't carry them.
_CANCELLABLE_STATUSES = frozenset({"requires_capture", "requires_action", "requires_confirmation"})
LOOKUP_EXPAND = ["data.latest_charge", "data.payment_method"]


def find_hold_payment_intents(hold: "AbstractCardHold") -> list[Any]:
    """Every PaymentIntent in Stripe whose metadata names ``hold`` (``card_hold_id``).

    Stripe's Search first (``metadata['card_hold_id']:'<id>'``). Search can lag about a
    minute behind and isn't offered in every region (India, say): when it refuses, the
    customer's PaymentIntents created since the first send (less :data:`LOOKUP_MARGIN`)
    are listed and filtered by the metadata. Stripe's transient errors propagate. Swap it
    with ``BASEAPP_PAYMENTS_CARD_HOLD_LOOKUP`` (a dotted path to a function of the hold).
    """
    return _search_metadata(
        hold, "card_hold_id", str(hold.pk), hold.placement_sent_at or hold.created
    )


def find_difference_payment_intents(hold: "AbstractCardHold") -> list[Any]:
    """The difference PaymentIntents in Stripe sent with ``hold``'s outstanding
    ``difference_key``: Search on ``metadata['difference_key']``, else the customer's
    PaymentIntents since the claim, as :func:`find_hold_payment_intents` does. Always this
    module's own lookup, never ``BASEAPP_PAYMENTS_CARD_HOLD_LOOKUP``: a project's lookup
    written for authorizations could miss a succeeded payment, and the difference would
    then be charged twice."""
    found = _search_metadata(
        hold, "difference_key", hold.difference_key, hold.difference_claimed_at or hold.created
    )
    return [
        payment_intent
        for payment_intent in found
        if _is_difference(payment_intent) and _metadata_hold_id(payment_intent) == str(hold.pk)
    ]


def _search_metadata(
    hold: "AbstractCardHold", field: str, value: str, since: datetime.datetime
) -> list[Any]:
    """The PaymentIntents whose ``metadata[field]`` is ``value``: Stripe's Search, or,
    when Search refuses (anything but a transient error), the hold's customer's
    PaymentIntents created since ``since`` (less :data:`LOOKUP_MARGIN`), filtered."""
    stripe_api = utils.get_stripe()
    try:
        found = stripe_api.PaymentIntent.search(
            query=f"metadata['{field}']:'{value}'", expand=LOOKUP_EXPAND, limit=100
        )
        return list(found.auto_paging_iter())
    except RETRYABLE_STRIPE_ERRORS:
        raise
    except stripe.StripeError:
        logger.warning(
            "PaymentIntent search refused for card hold %s; listing instead", hold.pk, exc_info=True
        )
    if not hold.stripe_customer_id:
        return []
    listed = stripe_api.PaymentIntent.list(
        customer=hold.stripe_customer_id,
        created={"gte": int((since - LOOKUP_MARGIN).timestamp())},
        expand=LOOKUP_EXPAND,
        limit=100,
    )
    return [
        payment_intent
        for payment_intent in listed.auto_paging_iter()
        if str(stripe_field(stripe_field(payment_intent, "metadata"), field) or "") == value
    ]


def _lookup(hold: "AbstractCardHold") -> list[Any]:
    """The project's lookup (``BASEAPP_PAYMENTS_CARD_HOLD_LOOKUP``), else
    :func:`find_hold_payment_intents`; only the PaymentIntents naming ``hold``, the ones
    that may hold money first, then oldest first. An override must return every
    PaymentIntent carrying the hold's ``card_hold_id``, in any status and of any kind. The
    difference is never looked up through it (:func:`find_difference_payment_intents`)."""
    from django.utils.module_loading import import_string

    configured = getattr(settings, "BASEAPP_PAYMENTS_CARD_HOLD_LOOKUP", None)
    lookup = import_string(configured) if configured else find_hold_payment_intents
    found = [pi for pi in lookup(hold) if _metadata_hold_id(pi) == str(hold.pk)]
    return sorted(
        found,
        key=lambda pi: (
            stripe_field(pi, "status") != "requires_capture",
            stripe_field(pi, "created") or 0,
        ),
    )


def _metadata_hold_id(payment_intent: Any) -> str:
    return str(stripe_field(stripe_field(payment_intent, "metadata"), "card_hold_id") or "")


def _forget_stray(card_hold_id: int, payment_intent_id: str) -> None:
    """Stripe confirmed a stray authorization is gone: stop re-driving its cancel."""
    with transaction.atomic():
        hold = _holds().objects.select_for_update().filter(pk=card_hold_id).first()
        strays = list(hold.stray_payment_intent_ids or []) if hold is not None else []
        if payment_intent_id in strays:
            strays.remove(payment_intent_id)
            hold.stray_payment_intent_ids = strays
            hold.save(update_fields=["stray_payment_intent_ids", "modified"])


def _track_stray(hold: "AbstractCardHold", payment_intent_id: str) -> None:
    """Under the hold's lock: record an authorization the hold doesn't carry and cancel
    it once this commits (the release task, pinned to it). The sweep re-drives the cancel
    until Stripe confirms it."""
    logger.warning(
        "Card hold %s: PaymentIntent %s isn't its own; cancelling it", hold.pk, payment_intent_id
    )
    hold.stray_payment_intent_ids = [*(hold.stray_payment_intent_ids or []), payment_intent_id]
    hold.save(update_fields=["stray_payment_intent_ids", "modified"])
    release_on_commit(hold.pk, claimed=True, payment_intent_id=payment_intent_id)


def _placement_outstanding(hold: "AbstractCardHold", payment_intent: Any) -> bool:
    """Whether ``payment_intent`` can be the answer to the scheduled hold's placement in
    flight: its key unsettled, and the amount and currency it was sent with."""
    return (
        hold.status == type(hold).Status.SCHEDULED
        and bool(hold.placement_key)
        and stripe_field(payment_intent, "amount") == hold.placement_amount_cents
        and stripe_field(payment_intent, "currency") == hold.currency
    )


def _send_outstanding(hold: "AbstractCardHold", payment_intent: Any) -> bool:
    """Whether ``payment_intent`` can be the answer to the on-session create in flight
    for this row (:func:`_begin_send`)."""
    return (
        hold.status == type(hold).Status.PENDING
        and hold.target_document_id is None
        and hold.stripe_payment_intent_id is None
        and bool(hold.placement_key)
        and str(stripe_field(stripe_field(payment_intent, "metadata"), "attempt_id"))
        == str(hold.attempt_id)
    )


def _apply_payment_intent(
    hold: "AbstractCardHold", target: Model | None, adapter: HoldTarget | None, payment_intent: Any
) -> str:
    """Under the target's lock, then the hold's: record what Stripe says of a
    PaymentIntent naming this hold, read live. Idempotent and order-free; no Stripe call
    (cancels run after the commit). Returns what it did:

    - ``current``: the hold's own PaymentIntent, nothing to record; ``confirmed`` when it
      confirms the hold's release (``canceled``); ``captured`` (``succeeded``,
      :func:`mark_captured`);
    - ``settled``: the answer of the scheduled hold's placement in flight, recorded as
      the placement records it (:func:`_settle_locked`: authorized, released for a target
      that can't take it, or failed for a decline);
    - ``recorded``: the answer of an on-session create in flight, recorded on its row as
      :func:`record_pending_hold` does (the client's retry carries on with it);
      ``declined`` for a decline;
    - ``recorded`` / ``declined`` / ``current``: the difference charged above a captured
      hold (``metadata['kind']`` ``difference``), recorded by :func:`_apply_difference`;
      a payment, never a stray;
    - ``stray``: any other authorization: cancelled and tracked until confirmed;
    - ``ignored``: nothing to do (another customer's, a decline that isn't the
      outstanding one, a stray already gone).
    """
    CardHold = type(hold)
    payment_intent_id = stripe_id(payment_intent)
    status = stripe_field(payment_intent, "status")
    if stripe_id(stripe_field(payment_intent, "customer")) != hold.stripe_customer_id:
        logger.warning(
            "PaymentIntent %s names card hold %s but not its customer; ignored",
            payment_intent_id,
            hold.pk,
        )
        return "ignored"
    if _is_difference(payment_intent):
        return _apply_difference(hold, payment_intent)
    if payment_intent_id == hold.stripe_payment_intent_id:
        if status == "succeeded":
            mark_captured(
                hold.pk,
                amount_cents=_amount_received(payment_intent),
                payment_intent_id=payment_intent_id,
            )
            return "captured"
        if (
            status == "canceled"
            and hold.status == CardHold.Status.RELEASED
            and hold.release_confirmed_at is None
        ):
            mark_released(hold.pk, payment_intent_id, confirmed=True)
            return "confirmed"
        return "current"
    strays = hold.stray_payment_intent_ids or []
    if payment_intent_id in strays:
        if status in _CANCELLABLE_STATUSES:
            return "stray"  # its cancel is under way, or re-driven by the sweep
        _forget_stray(hold.pk, payment_intent_id)
        return "confirmed"
    if status in _CANCELLABLE_STATUSES | {"requires_payment_method"}:
        if _placement_outstanding(hold, payment_intent):
            _settle_locked(
                hold,
                target,
                adapter,
                payment_intent,
                payment_intent_id,
                _placement_failure(payment_intent, None),
            )
            return "settled"
        if _send_outstanding(hold, payment_intent):
            return _record_send(hold, payment_intent)
    if status in _CANCELLABLE_STATUSES:
        _track_stray(hold, payment_intent_id)
        return "stray"
    if status == "succeeded":
        logger.error(
            "Card hold %s: PaymentIntent %s, which it doesn't carry, was captured; check Stripe",
            hold.pk,
            payment_intent_id,
        )
    return "ignored"


def _record_send(hold: "AbstractCardHold", payment_intent: Any) -> str:
    """Record an on-session create's PaymentIntent on its row (under the row's lock). A
    decline releases the row with it, as the first pass would (``abandoned``)."""
    CardHold = type(hold)
    payment_intent_id = stripe_id(payment_intent)
    amount = stripe_field(payment_intent, "amount") or hold.amount_cents
    hold.stripe_payment_intent_id = payment_intent_id
    hold.estimated_amount_cents = hold.amount_cents = amount
    for field, value in _CLEARED_SEND.items():
        setattr(hold, field, value)
    if stripe_field(payment_intent, "status") != "requires_payment_method":
        hold.save()
        return "recorded"
    hold.status = CardHold.Status.RELEASED
    hold.release_reason = CardHold.ReleaseReason.ABANDONED
    hold.save()
    send_on_commit(card_hold_released, hold_id=hold.pk)
    release_on_commit(hold.pk, claimed=True, payment_intent_id=payment_intent_id)
    return "declined"


def _locked_for(
    seen: "AbstractCardHold",
) -> tuple[bool, HoldTarget | None]:
    """Whether ``seen`` may be locked here, and its target's adapter (``None``: unlinked,
    or its target model isn't registered; a linked hold of an unregistered model is left
    alone)."""
    if seen.target_document_id is None:
        return True, None
    registered = _registered(seen)
    return registered is not None, registered[1] if registered is not None else None


def reconcile_payment_intent(card_hold_id: int, payment_intent_id: str) -> str:
    """Record what a PaymentIntent naming ``card_hold_id`` is now (the
    ``reconcile_card_hold`` task, queued by the Stripe webhook).

    The PaymentIntent is read from Stripe first, with no lock held, so the event's
    order, age and repeats don't matter: only its live state is recorded
    (:func:`_apply_payment_intent`). Its row is the one carrying it, else
    ``card_hold_id``, locked after its target. Stripe's transient errors propagate.
    """
    try:
        payment_intent = retrieve_payment_intent(payment_intent_id)
    except stripe.InvalidRequestError:
        logger.warning("Could not read PaymentIntent %s", payment_intent_id, exc_info=True)
        return "ignored"
    if _metadata_hold_id(payment_intent) != str(card_hold_id):
        return "ignored"
    rows = _holds().objects.select_related("target_document")
    for _lookup_pass in ("first", "after the row changed"):
        seen = (
            rows.filter(stripe_payment_intent_id=payment_intent_id).first()
            or rows.filter(pk=card_hold_id).first()
        )
        if seen is None:
            logger.warning(
                "PaymentIntent %s names card hold %s, which doesn't exist",
                payment_intent_id,
                card_hold_id,
            )
            return "ignored"
        lockable, adapter = _locked_for(seen)
        if not lockable:
            return "ignored"
        with transaction.atomic():
            target, hold = _lock_target_and_hold(seen, adapter)
            moved = (
                hold is None
                or seen.stripe_payment_intent_id == payment_intent_id
                and hold.stripe_payment_intent_id != payment_intent_id
            )
            if not moved:
                return _apply_payment_intent(hold, target, adapter, payment_intent)
    return "ignored"


def _apply_found(
    hold: "AbstractCardHold", target: Model | None, adapter: HoldTarget | None, found: list[Any]
) -> None:
    """:func:`_apply_payment_intent` for each PaymentIntent a lookup found, skipping any
    another row carries (that row's own flows settle it)."""
    ids = [stripe_id(payment_intent) for payment_intent in found]
    elsewhere = set(
        type(hold)
        .objects.filter(stripe_payment_intent_id__in=ids)
        .exclude(pk=hold.pk)
        .values_list("stripe_payment_intent_id", flat=True)
    )
    for payment_intent in found:
        if stripe_id(payment_intent) not in elsewhere:
            _apply_payment_intent(hold, target, adapter, payment_intent)


def _reconcile_placement(claim: _PlacementClaim) -> PlacementResult:
    """A scheduled hold's placement got no usable answer for :data:`PLACEMENT_KEY_TTL`:
    never replayed blind. Its authorizations are looked up in Stripe (no lock held), then,
    under the locks, the one answering it is recorded as the placement would record it,
    and any other cancelled (:func:`_apply_payment_intent`). With none found, the key is
    rotated (``placement_generation``) and the hold left ``scheduled`` with no key, for
    the next sweep to place afresh (``in_progress``)."""
    CardHold = _holds()
    seen = claim.hold
    try:
        found = _lookup(seen)
    except stripe.StripeError:
        logger.warning("Could not look up card hold %s in Stripe", seen.pk, exc_info=True)
        CardHold.objects.filter(pk=seen.pk, placement_claimed_at=claim.claimed_at).update(
            placement_claimed_at=None
        )
        return PlacementResult(PlacementStatus.IN_PROGRESS, hold=seen)
    with transaction.atomic():
        target, hold = _lock_target_and_hold(
            seen, claim.adapter, status=CardHold.Status.SCHEDULED, placement_key=seen.placement_key
        )
        if hold is None:
            return PlacementResult(PlacementStatus.IN_PROGRESS)
        _apply_found(hold, target, claim.adapter, found)
        hold.refresh_from_db()
        if hold.status == CardHold.Status.SCHEDULED and hold.placement_key == seen.placement_key:
            logger.warning(
                "Card hold %s: nothing in Stripe answers placement %s; placing afresh",
                hold.pk,
                seen.placement_key,
            )
            hold.placement_generation += 1
            hold.placement_claimed_at = None
            for field, value in _CLEARED_PLACEMENT.items():
                setattr(hold, field, value)
            hold.save()
            return PlacementResult(PlacementStatus.IN_PROGRESS, target=target, hold=hold)
    if hold.status == CardHold.Status.AUTHORIZED:
        return PlacementResult(PlacementStatus.PLACED, target=target, hold=hold)
    if hold.status == CardHold.Status.FAILED:
        return PlacementResult(PlacementStatus.DECLINED, target=target, hold=hold)
    return PlacementResult(PlacementStatus.REFUSED, target=target, hold=hold)


def reconcile_stale_send(card_hold_id: int) -> bool:
    """An on-session create with no usable answer for :data:`PLACEMENT_KEY_TTL` (the
    ``reconcile_card_hold`` task, queued by the sweep). Its attempt answers
    ``in_progress`` meanwhile and is never replayed. The row is claimed (a conditional
    UPDATE, committed before Stripe is called), its authorizations looked up, and then,
    under its lock, it is closed (``released``, ``abandoned``), so the attempt answers
    ``declined`` and the client starts a new one; whatever the lookup found is cancelled
    and tracked until Stripe confirms it. Whether it closed the row."""
    CardHold = _holds()
    now = timezone.now()
    stale = _sending(CardHold).filter(
        pk=card_hold_id, placement_sent_at__lt=now - PLACEMENT_KEY_TTL
    )
    if not stale.filter(
        Q(placement_claimed_at__isnull=True)
        | Q(placement_claimed_at__lt=now - PLACEMENT_CLAIM_TIMEOUT)
    ).update(placement_claimed_at=now):
        return False
    hold = CardHold.objects.get(pk=card_hold_id)
    try:
        found = _lookup(hold)
    except stripe.StripeError:
        logger.warning("Could not look up card hold %s in Stripe", hold.pk, exc_info=True)
        stale.filter(placement_claimed_at=now).update(placement_claimed_at=None)
        return False
    with transaction.atomic():
        hold = stale.select_for_update().filter(placement_claimed_at=now).first()
        if hold is None:
            return False
        _close_send(hold.pk)
        hold.refresh_from_db()
        _apply_found(hold, None, None, found)
    logger.warning(
        "Card hold %s: its on-session create was reconciled (%s found); attempt closed",
        card_hold_id,
        len(found),
    )
    return True


# --- Staff decisions on a failed hold ---------------------------------------------------


def _decide_failed(
    card_hold_id: int,
    decide: Callable[["AbstractCardHold", Model | None, Any], None],
    *,
    needs_adapter: bool = False,
) -> bool:
    """Run ``decide(hold, target, adapter)`` on a failed hold staff haven't kept, under
    the target's lock and then the hold's; whether it ran. No Stripe call.
    ``needs_adapter``: refuse (``False``, logged) a hold linked to a target model that
    is no longer registered, whose target nothing could act on."""
    CardHold = _holds()
    filters = {"status": CardHold.Status.FAILED, "kept_at__isnull": True}
    seen = _seen(card_hold_id, **filters)
    if seen is None:
        return False
    registered = _registered(seen)
    if needs_adapter and seen.target_document_id is not None and registered is None:
        logger.error(
            "Card hold %s: its target model isn't registered; the target can't be cancelled",
            seen.pk,
        )
        return False
    adapter = registered[1] if registered is not None else None
    with transaction.atomic():
        target, hold = _lock_target_and_hold(seen, adapter, **filters)
        if hold is None:
            return False
        decide(hold, target, adapter)
    return True


def keep_failed_hold(card_hold_id: int, actor: "AbstractBaseUser | None" = None) -> bool:
    """Staff keep the target of a failed hold: ``kept_at`` / ``kept_by`` are set, and the
    target later closes like one with no hold (:func:`capture` charges afresh, once).
    Only a ``failed`` hold not kept yet; kept is final. Whether it was kept."""

    def keep(hold: "AbstractCardHold", target: Model | None, adapter: Any) -> None:
        hold.kept_at = timezone.now()
        hold.kept_by = actor if getattr(actor, "is_authenticated", False) else None
        hold.save(update_fields=["kept_at", "kept_by", "modified"])

    return _decide_failed(card_hold_id, keep)


def cancel_failed_hold(card_hold_id: int, actor: "AbstractBaseUser | None" = None) -> bool:
    """Staff cancel the target of a failed hold: the adapter's ``cancel(target, actor)``
    runs under the locks, and the hold is ``released`` (``cancelled``, confirmed: nothing
    was held). Nothing is charged. Only a ``failed`` hold not kept; whether it ran. The
    hold stays failed for good (``failed_at``): it is never re-armed. A hold whose target
    model is no longer registered is refused (``False``, logged): its target can't be
    cancelled."""

    def cancel(hold: "AbstractCardHold", target: Model | None, adapter: Any) -> None:
        if target is not None:
            adapter.cancel(target, actor)
        CardHold = type(hold)
        hold.status = CardHold.Status.RELEASED
        hold.release_reason = CardHold.ReleaseReason.CANCELLED
        hold.release_confirmed_at = timezone.now()
        hold.save(update_fields=["status", "release_reason", "release_confirmed_at", "modified"])
        send_on_commit(card_hold_released, hold_id=hold.pk)

    return _decide_failed(card_hold_id, cancel, needs_adapter=True)


# --- A change of date -------------------------------------------------------------------


def reschedule(target: Model) -> PlacementResult | None:
    """Follow a change of ``target``'s date (``CARD_HOLDS_DEFERRAL_ENABLED`` only).

    Call it outside a transaction, after the new date is saved, or queue it with
    :func:`reschedule_on_commit`. Card holds don't watch the date themselves: only the
    project knows which field it is and when it changes.

    - an authorized hold whose new date is outside the window, or after its
      authorization expires, is released (``rescheduled``; Stripe is asked to cancel it)
      and the same row goes back to ``scheduled``, with its new ``hold_on`` (placed at
      once when that day has come);
    - a scheduled hold gets its new ``hold_on``; one whose date is now inside the window
      is placed off-session at once (:func:`place_scheduled`);
    - failed, kept, captured and released holds are left alone; ``None``.

    Answers ``scheduled``, ``placed``, ``declined`` (the placement failed),
    ``in_progress`` (a capture or placement is under way, or Stripe refused the cancel:
    retry), or ``None`` when nothing changed. Stripe's transient errors propagate.
    """
    if target.pk is None or not deferral_enabled():
        return None
    hold = _holds().objects.for_target(target).only("pk").first()
    return reschedule_hold(hold.pk) if hold is not None else None


def reschedule_on_commit(target: Model) -> None:
    """Queue :func:`reschedule` of ``target`` (the ``reschedule_card_hold`` task) once the
    current change commits: call it from the path that changes the target's date."""
    if target.pk is None or not deferral_enabled():
        return
    from .tasks import reschedule_card_hold

    CardHold = _holds()
    hold_ids = (
        CardHold.objects.for_target(target)
        .filter(status__in=(CardHold.Status.AUTHORIZED, CardHold.Status.SCHEDULED))
        .values_list("pk", flat=True)
    )
    for hold_id in list(hold_ids):
        transaction.on_commit(
            lambda hold_id=hold_id: reschedule_card_hold.delay(hold_id), robust=True
        )


def reschedule_hold(card_hold_id: int) -> PlacementResult | None:
    """:func:`reschedule`, by hold id (the ``reschedule_card_hold`` task, also queued by
    the sweep for a hold left released ``rescheduled`` or ``not_holdable``).

    While ``CARD_HOLDS_DEFERRAL_ENABLED`` is off (also for a task queued before it was
    turned off), only such a released hold is carried on: its cancel finished and the
    row put back to ``scheduled``, where it waits (nothing new is placed) and
    :func:`capture` charges it on the date. Anything else is left alone."""
    _ensure_outside_transaction()
    CardHold = _holds()
    seen = _seen(card_hold_id, target_document__isnull=False)
    if seen is None:
        return None
    registered = _registered(seen)
    if registered is None:
        return None
    adapter = registered[1]
    if (
        seen.status == CardHold.Status.RELEASED
        and seen.release_reason in CardHold.BACK_TO_SCHEDULED_REASONS
    ):
        if seen.release_confirmed_at is None:
            return _cancel_rescheduled(seen, adapter, seen.stripe_payment_intent_id)
        return _back_to_scheduled(seen, adapter)
    if not deferral_enabled():
        return None
    if seen.status == CardHold.Status.SCHEDULED:
        return _reschedule_scheduled(seen, adapter)
    if seen.status == CardHold.Status.AUTHORIZED:
        return _reschedule_placed(seen, adapter)
    return None


def _reschedule_scheduled(seen: "AbstractCardHold", adapter: HoldTarget) -> PlacementResult | None:
    CardHold = _holds()
    with transaction.atomic():
        target, hold = _lock_target_and_hold(seen, adapter, status=CardHold.Status.SCHEDULED)
        if hold is None or target is None:
            return None
        if hold.placement_key:
            return PlacementResult(PlacementStatus.IN_PROGRESS, target=target, hold=hold)
        hold_on = hold_on_for(adapter, target)
        if hold.hold_on != hold_on:
            hold.hold_on = hold_on
            hold.save(update_fields=["hold_on", "modified"])
    if hold_on <= _today():
        return place_scheduled(hold.pk)
    return PlacementResult(PlacementStatus.SCHEDULED, target=target, hold=hold)


def _expires_before_date(hold: "AbstractCardHold", adapter: HoldTarget, target: Model) -> bool:
    """Whether the hold's authorization lapses before its target's date begins (in the
    project's time zone), so it can't be captured on it."""
    target_date = adapter.target_date(target)
    if target_date is None or hold.expires_at is None:
        return False
    starts = timezone.make_aware(datetime.datetime.combine(target_date, datetime.time.min))
    return hold.expires_at < starts


def _reschedule_placed(seen: "AbstractCardHold", adapter: HoldTarget) -> PlacementResult | None:
    """An authorized hold whose date left the window, or moved past the authorization's
    expiry: released ``rescheduled`` under the locks, cancelled in Stripe with no lock
    held, then scheduled again on the same row (and placed at once when its day has
    come)."""
    CardHold = _holds()
    now = timezone.now()
    with transaction.atomic():
        target, hold = _lock_target_and_hold(seen, adapter, status=CardHold.Status.AUTHORIZED)
        if hold is None or target is None:
            return None
        if deferred_hold_on(adapter, target) is None and not _expires_before_date(
            hold, adapter, target
        ):
            return None
        if hold.charge_key or (
            hold.capture_claimed_at and hold.capture_claimed_at > now - CAPTURE_CLAIM_TIMEOUT
        ):
            return PlacementResult(PlacementStatus.IN_PROGRESS, target=target, hold=hold)
        payment_intent_id = hold.stripe_payment_intent_id
        _set_released(
            hold.pk,
            CardHold.ReleaseReason.RESCHEDULED,
            stripe_payment_intent_id=payment_intent_id,
        )
    return _cancel_rescheduled(seen, adapter, payment_intent_id)


def _cancel_rescheduled(
    seen: "AbstractCardHold", adapter: HoldTarget, payment_intent_id: str | None
) -> PlacementResult | None:
    """Cancel the authorization of a hold released ``rescheduled`` or ``not_holdable``
    (no lock held), then
    schedule the row again. Stripe's transient errors propagate, leaving it released
    and unconfirmed: a retry of :func:`reschedule_hold` (or the sweep) carries on."""
    outcome, _error = _cancel_payment_intent(payment_intent_id, seen.pk)
    if outcome == _Cancel.SUCCEEDED:
        _record_capture_from_stripe(seen.pk, payment_intent_id)
        return None
    if outcome == _Cancel.REFUSED:
        # Left released and unconfirmed: the sweep re-drives the cancel, then this.
        return PlacementResult(PlacementStatus.IN_PROGRESS, hold=seen)
    mark_released(seen.pk, payment_intent_id, confirmed=True)
    return _back_to_scheduled(seen, adapter)


def _back_to_scheduled(seen: "AbstractCardHold", adapter: HoldTarget) -> PlacementResult | None:
    """A hold released ``rescheduled`` (or ``not_holdable``), its cancel confirmed: the
    same row goes back to ``scheduled`` with its new ``hold_on`` (the replaced PaymentIntent joins
    ``previous_payment_intent_ids``), and is placed at once if that day has come. With
    ``CARD_HOLDS_DEFERRAL_ENABLED`` off it goes back all the same but isn't placed:
    :func:`capture` charges it on the date."""
    CardHold = _holds()
    with transaction.atomic():
        target, hold = _lock_target_and_hold(
            seen,
            adapter,
            status=CardHold.Status.RELEASED,
            release_reason__in=CardHold.BACK_TO_SCHEDULED_REASONS,
            release_confirmed_at__isnull=False,
            charge_key="",
            charged_at__isnull=True,
        )
        if hold is None:
            return None
        reason = _why_not_holdable(adapter, target)
        if reason:
            # Cancelled or done with the card meanwhile: it stays released, for that.
            hold.release_reason = reason
            hold.save(update_fields=["release_reason", "modified"])
            return None
        history = list(hold.previous_payment_intent_ids or [])
        if hold.stripe_payment_intent_id:
            history.append(hold.stripe_payment_intent_id)
        hold.previous_payment_intent_ids = history
        hold.stripe_payment_intent_id = None
        hold.status = CardHold.Status.SCHEDULED
        hold.hold_on = hold_on_for(adapter, target)
        hold.expires_at = None
        hold.release_reason = ""
        hold.release_confirmed_at = None
        hold.release_requested_at = None
        hold.placement_claimed_at = None
        for field, value in _CLEARED_PLACEMENT.items():
            setattr(hold, field, value)
        hold.save()
    logger.info("Card hold %s rescheduled for %s", hold.pk, hold.hold_on)
    if hold.hold_on <= _today() and deferral_enabled():
        return place_scheduled(hold.pk)
    return PlacementResult(PlacementStatus.SCHEDULED, target=target, hold=hold)


# --- Targets --------------------------------------------------------------------------


def open_hold_ids_for(target: Model) -> list[int]:
    """The ids of ``target``'s open holds, and of its scheduled ones."""
    if target.pk is None:
        return []
    return list(_holds().objects.for_target(target).releasable().values_list("pk", flat=True))


def release_target_holds_on_commit(target: Model) -> None:
    """Queue the release of ``target``'s open holds once the current change commits.

    Call it from every path that cancels a target. A target with no hold queues nothing.
    A scheduled hold is released too, with no Stripe call.
    """
    for hold_id in open_hold_ids_for(target):
        release_on_commit(hold_id)


def _active_targets_q() -> Q:
    """Holds on a registered target that is neither cancelled nor done with the card."""
    query = Q(pk__in=[])
    for model, adapter in get_targets().items():
        everything = model._default_manager.all()
        active = (
            model._default_manager.exclude(
                pk__in=Subquery(adapter.filter_cancelled(everything).values("pk"))
            )
            .exclude(pk__in=Subquery(adapter.filter_card_released(everything).values("pk")))
            .values("pk")
        )
        query |= Q(
            target_document__content_type=ContentType.objects.get_for_model(model),
            target_document__object_id__in=Subquery(active),
        )
    return query


def in_use_payment_method_ids(user: "AbstractBaseUser") -> set[str]:
    """Every PaymentMethod of this user that a hold still needs, in one query.

    In use: a hold, in any status, on a target that isn't cancelled and isn't done with
    the card; or a pending hold not linked yet, whatever its age (being placed). A
    project's card-removal path refuses to detach these.
    """
    CardHold = _holds()
    being_placed = Q(target_document__isnull=True, status=CardHold.Status.PENDING)
    return set(
        CardHold.objects.filter(customer=user)
        .filter(_active_targets_q() | being_placed)
        .exclude(stripe_payment_method_id="")
        .values_list("stripe_payment_method_id", flat=True)
    )


def card_in_use(user: "AbstractBaseUser", payment_method_id: str) -> bool:
    return payment_method_id in in_use_payment_method_ids(user)


__all__ = [
    "CHARGE_KEY_TTL",
    "DIFFERENCE_KIND",
    "attach_payments_to_invoice",
    "difference_idempotency_key",
    "hold_payment_intent_ids",
    "mark_paid_outside",
    "record_fees",
    "CaptureResult",
    "CaptureStatus",
    "CardHoldInTransaction",
    "HoldRefused",
    "PlacementResult",
    "PlacementStatus",
    "abandon_hold",
    "abandon_setup",
    "authorize_on_session",
    "cancel_failed_hold",
    "capturable_hold",
    "capture",
    "capture_idempotency_key",
    "charge_idempotency_key",
    "charged_later",
    "card_in_use",
    "clear_release_in_flight",
    "claim_orphan",
    "complete_on_session",
    "complete_setup_on_session",
    "deferred_hold_on",
    "find_attempt",
    "find_hold_payment_intents",
    "find_placed",
    "hold_amount_cents",
    "hold_on_for",
    "in_use_payment_method_ids",
    "keep_failed_hold",
    "mark_captured",
    "mark_release_in_flight",
    "mark_released",
    "open_hold_ids_for",
    "place_scheduled",
    "PLACEMENT_KEY_TTL",
    "reconcile_payment_intent",
    "reconcile_stale_send",
    "record_pending_hold",
    "record_pending_setup",
    "release",
    "release_for_charge",
    "release_on_commit",
    "release_target_holds_on_commit",
    "reschedule",
    "reschedule_hold",
    "reschedule_on_commit",
    "scheduled_idempotency_key",
    "setup_idempotency_key",
    "usable_payment_method",
]
