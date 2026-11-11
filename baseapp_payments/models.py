from typing import TYPE_CHECKING, Any

import swapper
from constance import config
from django.apps import apps
from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ObjectDoesNotExist
from django.db import models
from django.utils.translation import gettext_lazy as _
from model_utils.models import TimeStampedModel

from baseapp_core.models import DocumentId

try:
    # Optional: `RelayModel` lives in baseapp_core.graphql, which needs the `graphql`
    # extra. It adds no columns, so a REST-only install gets the same table without it.
    from baseapp_core.graphql.models import RelayModel
except ImportError:  # pragma: no cover - the test project always has the graphql extra

    class RelayModel(models.Model):  # type: ignore[no-redef]
        class Meta:
            abstract = True


if TYPE_CHECKING:
    from baseapp_core.graphql import DjangoObjectType


class BaseCustomer(TimeStampedModel):
    entity_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        verbose_name=_("entity type"),
        # Abstract and swappable, so a literal name would clash between the
        # concrete Customer of any two apps that both subclass this.
        related_name="%(app_label)s_%(class)ss",
    )
    entity_id = models.PositiveIntegerField(_("entity id"))
    entity = GenericForeignKey("entity_type", "entity_id")
    remote_customer_id = models.CharField(_("remote customer id"), max_length=255)

    class Meta:
        abstract = True
        swappable = swapper.swappable_setting("baseapp_payments", "Customer")
        verbose_name = _("customer")
        verbose_name_plural = _("customers")
        # One Customer per billed entity. Dropped incidentally by the invoice-endpoint
        # commit (#305); without it two concurrent requests for the same profile each
        # create a row, and each row gets its own Stripe customer.
        unique_together = ("entity_type", "entity_id")

    def __str__(self) -> str:
        return f"{self.entity} - {self.remote_customer_id}"

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not hasattr(self, "tracker"):
            raise RuntimeError(
                'BaseCustomer requires `tracker = FieldTracker(["entity"])`.'
                " Please ensure your concrete Customer model includes this tracker."
            )

        if not self.entity_type_id:
            try:
                # A dotted label, not a class. get_for_model reads model._meta, so
                # handing it the string raised AttributeError and this except turned
                # that into a config error - the fallback could never succeed.
                entity_model = apps.get_model(config.STRIPE_CUSTOMER_ENTITY_MODEL)
                self.entity_type = ContentType.objects.get_for_model(entity_model)
            except (LookupError, ValueError) as e:
                raise ValueError(f"Invalid STRIPE_CUSTOMER_ENTITY_MODEL configuration: {e}") from e

        if self.tracker.has_changed("entity") or not self.entity_id:
            if self.entity is not None:
                new_entity_type = ContentType.objects.get_for_model(self.entity)
                if new_entity_type != self.entity_type:
                    raise ValueError(
                        "Entity type is not the one configured in STRIPE_CUSTOMER_ENTITY_MODEL"
                    )
                self.entity_id = self.entity.id
            elif not self.entity_type:
                raise ValueError("Entity type must be set when entity is None")

        super().save(*args, **kwargs)


class BaseSubscription(TimeStampedModel):
    # A FK rather than master's remote_customer_id string: the subscription webhook
    # has to resolve the local Customer row, and matching on the Stripe id meant a
    # lookup that silently created orphans when it missed.
    customer = models.ForeignKey(
        swapper.get_model_name("baseapp_payments", "Customer"),
        on_delete=models.CASCADE,
        related_name="subscriptions",
        verbose_name=_("customer"),
    )
    # Unique on its own rather than paired with the customer: the viewset resolves a
    # subscription with lookup_field="remote_subscription_id" and the webhook handler
    # filters on it alone, so a second row with the same id is MultipleObjectsReturned
    # on read and a multi-row delete on cancellation. A Stripe subscription id belongs
    # to exactly one customer anyway, which the old (customer, id) pair did not say.
    remote_subscription_id = models.CharField(
        _("remote subscription id"), max_length=255, unique=True
    )

    class Meta:
        abstract = True
        swappable = swapper.swappable_setting("baseapp_payments", "Subscription")
        verbose_name = _("subscription")
        verbose_name_plural = _("subscriptions")


# --- Card holds -------------------------------------------------------------------------
# Opt-in: nothing below runs for a project that sets no BASEAPP_PAYMENTS_CARDHOLD_MODEL.


def card_holds_enabled() -> bool:
    """Whether the project declares a concrete card hold model.

    A project that uses only the REST customer and subscription endpoints sets no
    ``BASEAPP_PAYMENTS_CARDHOLD_MODEL`` and gets no hold behaviour.
    """
    return bool(swapper.is_swapped("baseapp_payments", "CardHold"))


def get_card_hold_model() -> type[models.Model]:
    """The concrete card hold model. Raises ``ImproperlyConfigured`` when none is set."""
    return swapper.load_model("baseapp_payments", "CardHold")


# The reverse path from a documentable target to its hold: the target's ``document``
# GenericRelation (DocumentIdMixin), then DocumentId's one-to-one ``card_hold``. Prefetch
# it (``prefetch_related(CARD_HOLD_PREFETCH_PATH)``) to read many targets' holds at once.
CARD_HOLD_PREFETCH_PATH = "document__card_hold"
NOT_PREFETCHED = object()


def prefetched_card_hold(target: models.Model) -> Any:
    """The hold prefetched onto ``target`` through :data:`CARD_HOLD_PREFETCH_PATH`,
    ``None`` when it has none, or :data:`NOT_PREFETCHED` when nothing was prefetched (a
    single object, a path that didn't prefetch). No query."""
    if "document" not in getattr(target, "_prefetched_objects_cache", {}):
        return NOT_PREFETCHED
    document = next(iter(target.document.all()), None)
    if document is None:
        return None
    if not type(document).card_hold.is_cached(document):
        return NOT_PREFETCHED
    try:
        return document.card_hold
    except ObjectDoesNotExist:
        return None


class CardHoldQuerySet(models.QuerySet):
    def releasable(self) -> "CardHoldQuerySet":
        """Open holds, and the ones that only saved the card (``scheduled``, ``saved``:
        released without a Stripe call)."""
        return self.filter(status__in=(*self.model.OPEN_STATUSES, *self.model.UNPLACED_STATUSES))

    def for_target(self, target: models.Model) -> "CardHoldQuerySet":
        """The holds attached to ``target`` through its ``DocumentId``."""
        return self.filter(
            target_document__content_type=ContentType.objects.get_for_model(target),
            target_document__object_id=target.pk,
        )


class AbstractCardHold(RelayModel, TimeStampedModel):
    """An authorization (a manual-capture PaymentIntent) placed on a customer's card.

    Created ``pending`` when the PaymentIntent is created, linked to its target (any
    registered model, through ``DocumentId``) and ``authorized`` once the project's own
    record is placed. Later it is ``captured`` for the final amount, or ``released`` (its
    PaymentIntent cancelled).

    A target whose adapter doesn't use holds (``uses_holds = False``) gets a ``saved``
    row instead: the card saved with a SetupIntent, nothing ever authorized, and the
    target charged directly on its date through ``capture()``, which records the charge
    here.

    Holds placed later, without the customer present (``CARD_HOLDS_DEFERRAL_ENABLED``):
    a target dated further out than the window gets a ``scheduled`` hold, with the card
    saved (a SetupIntent) and nothing authorized until ``hold_on``. The sweep then places
    it off-session: ``authorized``, or ``failed`` when Stripe refuses, which is final.
    Staff decide a failed hold: kept (``kept_at``; the target closes by a fresh charge)
    or cancelled (``released``, the target cancelled through its adapter).
    """

    class Status(models.TextChoices):
        PENDING = "pending", _("Pending")
        AUTHORIZED = "authorized", _("Authorized")
        RELEASED = "released", _("Released")
        CAPTURED = "captured", _("Captured")
        SCHEDULED = "scheduled", _("Scheduled")
        FAILED = "failed", _("Failed")
        SAVED = "saved", _("Card saved, charged on the date")

    class FundingType(models.TextChoices):
        CREDIT = "credit", _("Credit")
        DEBIT = "debit", _("Debit")
        PREPAID = "prepaid", _("Prepaid")
        UNKNOWN = "unknown", _("Unknown")

    class ReleaseReason(models.TextChoices):
        """Why a hold was released: only ``for_charge`` keeps it from being re-armed."""

        ABANDONED = "abandoned", _("Never placed")
        CANCELLED = "cancelled", _("Target cancelled")
        CARD_RELEASED = "card_released", _("Target done with the card")
        DECLINED = "declined", _("Capture declined")
        FOR_CHARGE = "for_charge", _("Released to charge afresh")
        LAPSED = "lapsed", _("Authorization ended in Stripe")
        RESCHEDULED = "rescheduled", _("Target moved out of the window")
        NOT_HOLDABLE = "not_holdable", _("Target can't take a hold now")

    class ChargeBlock(models.TextChoices):
        """Why ``capture()`` must never charge this hold on its own: an earlier call
        refused to, and a retry must not undo that. Decide by hand."""

        DECLINED = "declined", _("The card declined the capture")
        LAPSED = "lapsed", _("The authorization was cancelled outside capture()")
        STALE_CHARGE = "stale_charge", _("A charge that never finished, past Stripe's 24 hours")

    # Holds that may still have a live authorization in Stripe.
    OPEN_STATUSES = (Status.PENDING, Status.AUTHORIZED)
    # Linked holds that saved the card and authorized nothing (yet, or ever).
    UNPLACED_STATUSES = (Status.SCHEDULED, Status.SAVED)
    # Released only to go back to ``scheduled`` once Stripe confirms the cancel: the date
    # left the window, or a placement authorized for a target outside ``filter_holdable``.
    BACK_TO_SCHEDULED_REASONS = (ReleaseReason.RESCHEDULED, ReleaseReason.NOT_HOLDABLE)

    # PROTECT, on purpose: a customer with any hold row (payment history) can't be
    # deleted out from under it, so baseapp_auth's account deletion fails for them.
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="card_holds",
        verbose_name=_("customer"),
    )
    stripe_customer_id = models.CharField(_("Stripe customer id"), max_length=255, blank=True)
    # Not DocumentIdUniqueTargetMixin: a hold exists, unlinked, before its target does.
    # SET_NULL so a target can still be deleted; a pre_delete receiver releases its hold
    # first (baseapp_payments.signals).
    target_document = models.OneToOneField(
        DocumentId,
        on_delete=models.SET_NULL,
        related_name="card_hold",
        verbose_name=_("target document"),
        null=True,
        blank=True,
    )
    attempt_id = models.UUIDField(_("attempt id"))
    stripe_payment_intent_id = models.CharField(
        _("Stripe PaymentIntent id"), max_length=255, unique=True, null=True, blank=True
    )
    stripe_setup_intent_id = models.CharField(
        _("Stripe SetupIntent id"), max_length=255, unique=True, null=True, blank=True
    )
    stripe_payment_method_id = models.CharField(_("Stripe PaymentMethod id"), max_length=255)
    card_brand = models.CharField(_("card brand"), max_length=32, blank=True)
    card_last4 = models.CharField(_("card last four"), max_length=4, blank=True)
    card_exp_month = models.PositiveSmallIntegerField(_("card expiry month"), default=0)
    card_exp_year = models.PositiveSmallIntegerField(_("card expiry year"), default=0)
    card_funding = models.CharField(
        _("card funding"),
        max_length=10,
        choices=FundingType.choices,
        default=FundingType.UNKNOWN,
    )
    # The same for every PaymentMethod of one physical card; "" when Stripe sent none.
    card_fingerprint = models.CharField(_("card fingerprint"), max_length=64, blank=True)
    currency = models.CharField(_("currency"), max_length=3, default="usd")
    # The amount the target is expected to cost, from the project's pricing.
    estimated_amount_cents = models.PositiveIntegerField(_("estimated amount (cents)"))
    buffer_percent = models.DecimalField(_("buffer (%)"), max_digits=5, decimal_places=2)
    # The amount authorized: ceil(estimated × (1 + buffer / 100)).
    amount_cents = models.PositiveIntegerField(_("amount held (cents)"))
    status = models.CharField(
        _("status"), max_length=10, choices=Status.choices, default=Status.PENDING
    )
    # When Stripe stops honouring the authorization (the charge's capture_before).
    expires_at = models.DateTimeField(_("expires at"), null=True, blank=True)
    # A scheduled hold: the day the sweep places it (the target's date minus the window).
    hold_on = models.DateField(_("hold on"), null=True, blank=True)
    # A hold placed later, without the customer present, that Stripe refused.
    failed_at = models.DateTimeField(_("failed at"), null=True, blank=True)
    failure_code = models.CharField(_("failure code"), max_length=64, blank=True)
    # A staff member chose to keep the target despite the failed hold.
    kept_at = models.DateTimeField(_("kept at"), null=True, blank=True)
    kept_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="kept_card_holds",
        verbose_name=_("kept by"),
        null=True,
        blank=True,
    )
    # A PaymentIntent create sent to Stripe whose outcome isn't recorded yet: its
    # idempotency key, amount and claim time. A deferred placement (``scheduled``), or an
    # on-session one (a ``pending`` row written before the create, with no PaymentIntent).
    placement_key = models.CharField(_("placement key"), max_length=255, blank=True)
    placement_amount_cents = models.PositiveIntegerField(
        _("placement amount (cents)"), null=True, blank=True
    )
    placement_claimed_at = models.DateTimeField(_("placement claimed at"), null=True, blank=True)
    # When ``placement_key`` was first sent; replays never move it. Stripe may forget a key
    # after 24 hours, so past PLACEMENT_KEY_TTL the create is reconciled, not replayed.
    placement_sent_at = models.DateTimeField(_("placement first sent at"), null=True, blank=True)
    # Bumped when a reconciled placement found nothing in Stripe: a new key for the next one.
    placement_generation = models.PositiveSmallIntegerField(_("placement generation"), default=0)
    # Authorizations made for this hold that it doesn't carry (a lost answer's, found by a
    # webhook or a lookup): each is cancelled, and re-driven by the sweep until confirmed.
    stray_payment_intent_ids = models.JSONField(
        _("stray PaymentIntent ids"), default=list, blank=True
    )
    # Audit trail of re-arming: the PaymentIntents and attempts this row held before,
    # oldest first. A retried earlier attempt still finds its target through these.
    previous_payment_intent_ids = models.JSONField(
        _("previous PaymentIntent ids"), default=list, blank=True
    )
    previous_attempt_ids = models.JSONField(_("previous attempt ids"), default=list, blank=True)
    # ``released`` is written when the release is decided, sometimes before Stripe has
    # cancelled the PaymentIntent. This is set once Stripe confirmed it (or the
    # authorization lapsed); until then the sweep re-drives the cancel.
    release_confirmed_at = models.DateTimeField(_("release confirmed at"), null=True, blank=True)
    # A release task is working on this hold (stamped at each attempt): the sweep leaves
    # it alone for a while instead of queuing a duplicate.
    release_requested_at = models.DateTimeField(_("release requested at"), null=True, blank=True)
    captured_amount_cents = models.PositiveIntegerField(
        _("captured amount (cents)"), null=True, blank=True
    )
    captured_at = models.DateTimeField(_("captured at"), null=True, blank=True)
    # Set with ``released``: a hold released to be charged afresh is never re-armed.
    release_reason = models.CharField(
        _("release reason"), max_length=16, choices=ReleaseReason.choices, blank=True
    )
    # A capture call is working on this hold (a conditional UPDATE claims it): a
    # concurrent capture answers ``in_progress`` instead of calling Stripe too.
    capture_claimed_at = models.DateTimeField(_("capture claimed at"), null=True, blank=True)
    # The charge-instead claim: the idempotency key handed to the project's ``charge``,
    # written before it runs, and when it returned. Once ``charged_at`` is set, a repeated
    # capture answers from these and never charges again.
    charge_key = models.CharField(_("charge idempotency key"), max_length=255, blank=True)
    # When the charge claim was written: Stripe forgets an idempotency key after 24 hours,
    # so a charge claimed longer ago than that is never re-run blind.
    charge_claimed_at = models.DateTimeField(_("charge claimed at"), null=True, blank=True)
    # How many charges Stripe definitely refused (a decline): the next charge's key is
    # ``{prefix}-charge-{hold}-{charge_generation}``, so it isn't the refused one replayed.
    charge_generation = models.PositiveSmallIntegerField(_("charge generation"), default=0)
    charged_at = models.DateTimeField(_("charged at"), null=True, blank=True)
    # Set when a capture refused to charge (a decline, an authorization cancelled outside
    # capture(), a charge too old to replay): no later capture() charges automatically.
    charge_blocked_reason = models.CharField(
        _("charge blocked reason"), max_length=16, choices=ChargeBlock.choices, blank=True
    )

    objects = CardHoldQuerySet.as_manager()

    class Meta:
        abstract = True
        swappable = swapper.swappable_setting("baseapp_payments", "CardHold")
        verbose_name = _("card hold")
        verbose_name_plural = _("card holds")
        ordering = ["-created", "-pk"]
        indexes = [
            models.Index(fields=["customer", "attempt_id"], name="%(app_label)s_chold_attempt"),
            models.Index(fields=["status", "created"], name="%(app_label)s_chold_status"),
            models.Index(fields=["status", "hold_on"], name="%(app_label)s_chold_hold_on"),
        ]
        constraints = [
            # One row per key in flight: two concurrent first passes of one attempt can't
            # each write a row and send the same key with different metadata.
            models.UniqueConstraint(
                fields=["placement_key"],
                condition=~models.Q(placement_key=""),
                name="%(app_label)s_chold_placement_key",
            ),
        ]

    def __str__(self) -> str:
        return self.stripe_payment_intent_id or self.stripe_setup_intent_id or f"#{self.pk}"

    @classmethod
    def get_graphql_object_type(cls) -> type["DjangoObjectType"]:
        from .graphql.object_types import CardHoldObjectType

        return CardHoldObjectType

    @property
    def target(self) -> models.Model | None:
        """The object this hold is attached to, or ``None`` (unlinked, or deleted)."""
        if not self.target_document_id:
            return None
        return self.target_document.content_object
