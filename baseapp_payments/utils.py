import datetime
import logging
from dataclasses import dataclass
from types import ModuleType
from typing import TYPE_CHECKING, Any

import stripe
import swapper
from constance import config
from django.apps import apps
from django.conf import settings
from django.db import IntegrityError, transaction
from django.http import HttpRequest, JsonResponse
from django.utils import timezone

if TYPE_CHECKING:
    from django.contrib.auth.base_user import AbstractBaseUser

logger = logging.getLogger(__name__)

Customer = swapper.load_model("baseapp_payments", "Customer")
Subscription = swapper.load_model("baseapp_payments", "Subscription")


# The statuses that mean the customer still has a billing relationship. Stripe's list
# filter takes one value or "all", so this cannot be handed to the API - callers ask for
# "all" and narrow with this.
STRIPE_LIVE_SUBSCRIPTION_STATUSES = frozenset(
    {"active", "trialing", "past_due", "unpaid", "incomplete"}
)


# Anything outside this set makes the Stripe API raise, which surfaced as a 500 for a
# caller-supplied query parameter.
STRIPE_SUBSCRIPTION_LIST_STATUSES = frozenset(
    {
        "active",
        "all",
        "canceled",
        "ended",
        "incomplete",
        "incomplete_expired",
        "past_due",
        "paused",
        "trialing",
        "unpaid",
    }
)


def stripe_field(
    obj: "stripe.StripeObject | dict[str, Any] | str | None", field: str, default: Any = None
) -> Any:
    """``obj[field]``, tolerating ``obj`` arriving as a bare id string or None.

    ``expand`` is a request, not a guarantee. The same field comes back as the object
    on one call and as its id on the next, and reading the id like an object is what
    raised ``'str' object has no attribute 'get'`` partway through subscribing.
    """
    if obj is None or isinstance(obj, str):
        return default
    if isinstance(obj, dict):
        return obj.get(field, default)
    return getattr(obj, field, default)


def stripe_id(value: "stripe.StripeObject | dict[str, Any] | str | None") -> "str | None":
    """The id of an expandable field, whichever shape Stripe sent."""
    if value is None or isinstance(value, str):
        return value
    return stripe_field(value, "id")


def _empty_list_object(url: str) -> "stripe.ListObject":
    """An empty Stripe ``ListObject``.

    Callers page over every ``list_*`` result, so a "nothing found" answer has to
    support ``auto_paging_iter()`` too - a bare ``[]`` would raise instead.
    """
    return stripe.ListObject.construct_from(
        {"object": "list", "data": [], "has_more": False, "url": url}, stripe.api_key
    )


# The PaymentIntent events card holds reconcile from (see "Card holds" in the README).
CARD_HOLD_EVENTS = (
    "payment_intent.amount_capturable_updated",
    "payment_intent.canceled",
    "payment_intent.succeeded",
    "payment_intent.payment_failed",
)


def invoice_client_secret(invoice: Any) -> "str | None":
    """The client secret that confirms an invoice's payment: ``confirmation_secret``
    (API 2025-03-31.basil and later; only present when expanded), or, from an invoice
    rendered at an older version, its expanded ``payment_intent``."""
    secret = stripe_field(stripe_field(invoice, "confirmation_secret"), "client_secret")
    if secret:
        return secret
    return stripe_field(stripe_field(invoice, "payment_intent"), "client_secret")


def subscription_period(subscription: Any, field: str) -> Any:
    """``current_period_start`` / ``current_period_end`` of a subscription: on its items
    from API 2025-03-31.basil on (each item has its own; the earliest end is the next
    renewal), on the subscription itself before."""
    value = stripe_field(subscription, field)
    if value:
        return value
    items = stripe_field(stripe_field(subscription, "items"), "data") or []
    values = [stripe_field(item, field) for item in items]
    values = [value for value in values if value]
    if not values:
        return None
    return min(values) if field == "current_period_end" else max(values)


class StripeWebhookHandler:
    def __init__(self) -> None:
        self.EVENT_HANDLERS = {
            "customer.created": self.customer_created,
            "customer.deleted": self.customer_deleted,
            "customer.subscription.created": self.subscription_created,
            "customer.subscription.deleted": self.subscription_deleted,
            **{event_type: self.card_hold_payment_intent for event_type in CARD_HOLD_EVENTS},
        }

    @staticmethod
    def card_hold_payment_intent(event: "stripe.Event") -> JsonResponse:
        """A PaymentIntent event for a card hold (``metadata['card_hold_id']``): queue
        ``reconcile_card_hold``, which reads the PaymentIntent live and records it, so the
        event's order and repeats don't matter. Nothing is read or written here, and
        without card holds (or without the metadata) the event is just acknowledged. A
        broker error answers 500, so Stripe delivers the event again."""
        from .models import card_holds_enabled

        if not card_holds_enabled():
            return JsonResponse({"status": "success"}, status=200)
        payment_intent = event["data"]["object"]
        card_hold_id = str(
            stripe_field(stripe_field(payment_intent, "metadata"), "card_hold_id") or ""
        )
        if not card_hold_id.isdigit():
            return JsonResponse({"status": "success"}, status=200)
        from .tasks import reconcile_card_hold

        try:
            reconcile_card_hold.delay(
                int(card_hold_id), payment_intent_id=stripe_id(payment_intent)
            )
        except Exception:
            logger.exception("Could not queue the reconcile of card hold %s", card_hold_id)
            return JsonResponse({"error": "Error"}, status=500)
        return JsonResponse({"status": "success"}, status=200)

    @staticmethod
    def customer_created(event: "stripe.Event") -> JsonResponse:
        customer_data = event["data"]["object"]
        try:
            existing_customer = Customer.objects.filter(
                remote_customer_id=customer_data["id"]
            ).first()
            if existing_customer:
                return JsonResponse({"status": "success"}, status=200)
            entity_id = customer_data["metadata"].get("entity_id")
            entity_model = apps.get_model(config.STRIPE_CUSTOMER_ENTITY_MODEL)
            entity = entity_model.objects.get(id=entity_id)
            try:
                with transaction.atomic():
                    Customer.objects.create(entity=entity, remote_customer_id=customer_data["id"])
            except IntegrityError:
                # The API creates the Stripe customer before inserting its row, so this event
                # can arrive while that insert is uncommitted: the check above misses it, and
                # this insert waits on it and fails once it commits. Same remote id means the
                # row we wanted is there; anything else is a real conflict.
                if not Customer.objects.filter(remote_customer_id=customer_data["id"]).exists():
                    raise
            return JsonResponse({"status": "success"}, status=200)
        except Exception as e:
            logger.exception(e)
            return JsonResponse({"error": "Error"}, status=500)

    @staticmethod
    def customer_deleted(event: "stripe.Event") -> JsonResponse:
        customer_data = event["data"]["object"]
        try:
            Customer.objects.filter(remote_customer_id=customer_data["id"]).delete()
            return JsonResponse({"status": "success"}, status=200)
        except Exception as e:
            logger.exception(e)
            return JsonResponse({"error": "Error"}, status=500)

    @staticmethod
    def subscription_created(event: "stripe.Event") -> JsonResponse:
        subscription_data = event["data"]["object"]
        try:
            existing_subscription = Subscription.objects.filter(
                remote_subscription_id=subscription_data["id"]
            ).first()
            if existing_subscription:
                return JsonResponse({"status": "success"}, status=200)
            customer = Customer.objects.filter(
                remote_customer_id=subscription_data["customer"]
            ).first()
            if not customer:
                # Stripe can deliver this before customer.created; a non-2xx makes it
                # retry, by which time the customer row should exist.
                logger.warning(
                    "Subscription webhook for unknown customer %s", subscription_data["customer"]
                )
                return JsonResponse({"error": "Error"}, status=500)
            Subscription.objects.create(
                customer=customer,
                remote_subscription_id=subscription_data["id"],
            )
            return JsonResponse({"status": "success"}, status=200)
        except Exception as e:
            logger.exception(e)
            return JsonResponse({"error": "Error"}, status=500)

    @staticmethod
    def subscription_deleted(event: "stripe.Event") -> JsonResponse:
        subscription_data = event["data"]["object"]
        try:
            Subscription.objects.filter(remote_subscription_id=subscription_data["id"]).delete()
            return JsonResponse({"status": "success"}, status=200)
        except Exception as e:
            logger.exception(e)
            return JsonResponse({"error": "Error"}, status=500)

    def webhook_handler(self, request: HttpRequest, secret: str) -> JsonResponse:
        payload = request.body
        sig_header = request.META.get("HTTP_STRIPE_SIGNATURE")
        if not sig_header:
            logger.warning("Stripe webhook received without a signature header")
            return JsonResponse({"error": "Error"}, status=400)
        endpoint_secret = secret

        try:
            event = stripe.Webhook.construct_event(payload, sig_header, endpoint_secret)
        except ValueError as e:
            logger.exception(e)
            return JsonResponse({"error": "Error"}, status=400)
        except stripe.error.SignatureVerificationError as e:
            logger.exception(e)
            return JsonResponse({"error": "Error"}, status=400)

        event_type = event["type"]
        handler = self.EVENT_HANDLERS.get(event_type)

        if handler:
            return handler(event)
        else:
            # if event is not handled, return 200 so stripe doesn't keep resending
            return JsonResponse({"status": "success"}, status=200)


class CustomerCreationError(Exception):
    pass


class CustomerNotFound(Exception):
    pass


class CustomerOwnershipError(Exception):
    pass


class CustomerUpdateError(Exception):
    pass


class PaymentIntendNotFound(Exception):
    pass


class PaymentMethodNotFound(Exception):
    pass


class PaymentMethodUpdateError(Exception):
    pass


class PaymentMethodDeletionError(Exception):
    pass


class SetupIntentCreationError(Exception):
    pass


class PriceRetrievalError(Exception):
    pass


class InvoiceNotFound(Exception):
    pass


class SubscriptionCreationError(Exception):
    pass


class SubscriptionNotFound(Exception):
    pass


# Basil (2025-03-31) moved the subscription's billing period to its items, replaced the
# invoice's single payment_intent with ``payments`` / ``confirmation_secret``, and lets
# several PaymentIntents pay one invoice (``Invoice.attach_payment``, which card holds use
# for a payment above the hold). Set your webhook endpoint to this version too: Stripe
# renders each event at the endpoint's version, not this one. See the README.
DEFAULT_STRIPE_API_VERSION = "2025-05-28.basil"


def configure_stripe(api_key: str | None = None, api_version: str | None = None) -> None:
    """Set the ``stripe`` module's key and API version, from settings unless given.

    Read at call time, not import time, so a changed setting (or a test override) applies.
    """
    stripe.api_key = settings.STRIPE_SECRET_KEY if api_key is None else api_key
    stripe.api_version = (
        getattr(settings, "STRIPE_API_VERSION", DEFAULT_STRIPE_API_VERSION)
        if api_version is None
        else api_version
    )


class StripeService:
    def __init__(self, api_key: str | None = None, api_version: str | None = None) -> None:
        configure_stripe(api_key, api_version)

    def create_customer(self, **kwargs: Any) -> "stripe.Customer":
        try:
            return stripe.Customer.create(**kwargs)
        except Exception as e:
            logger.exception(e)
            raise CustomerCreationError("Error creating customer in Stripe")

    def retrieve_customer(
        self, customer_id: "str | None" = None, email: "str | None" = None
    ) -> "stripe.Customer | None":
        try:
            if not customer_id and email:
                escaped_email = email.replace("\\", "\\\\").replace("'", "\\'")
                results = stripe.Customer.search(query=f"email:'{escaped_email}'")
                if results.data:
                    return results.data[0]
                else:
                    return None
            return stripe.Customer.retrieve(customer_id)
        except stripe.error.InvalidRequestError as e:
            if "No such customer" in str(e):
                return None
            logger.exception(e)
            raise CustomerNotFound("Error retrieving customer in Stripe")
        except Exception as e:
            logger.exception(e)
            raise CustomerNotFound("Error retrieving customer in Stripe")

    def update_customer(self, customer_id: str, **kwargs: Any) -> "stripe.Customer":
        try:
            return stripe.Customer.modify(customer_id, **kwargs)
        except Exception as e:
            logger.exception(e)
            raise CustomerUpdateError("Error updating customer in Stripe")

    def delete_customer(self, customer_id: str) -> "stripe.Customer | None":
        try:
            response = stripe.Customer.delete(customer_id)
            return response
        except stripe.error.InvalidRequestError as e:
            if "No such customer" in str(e):
                return None
            logger.exception(e)
            raise CustomerNotFound("Error deleting customer in Stripe")
        except Exception as e:
            logger.exception(e)
            raise CustomerNotFound("Error deleting customer in Stripe")

    def create_subscription(self, customer_id: str, price_id: str) -> "stripe.Subscription":
        try:
            subscription = stripe.Subscription.create(
                customer=customer_id,
                items=[{"price": price_id}],
            )
            return subscription
        except Exception as e:
            logger.exception(e)
            raise SubscriptionCreationError("Error creating subscription in Stripe")

    def create_incomplete_subscription(
        self,
        customer_id: str,
        price_id: str,
        payment_method_id: "str | None" = None,
        product_id: "str | None" = None,
    ) -> "stripe.Subscription":
        try:
            subscription = stripe.Subscription.create(
                customer=customer_id,
                items=[{"price": price_id}],
                default_payment_method=payment_method_id,
                payment_behavior="default_incomplete",
                payment_settings={"save_default_payment_method": "on_subscription"},
                # Basil removed invoice.payment_intent: the secret the frontend confirms
                # is the invoice's confirmation_secret (includable, so only when asked).
                expand=["latest_invoice.confirmation_secret"],
                metadata={"product_id": product_id} if product_id else None,
            )
            latest_invoice = subscription.get("latest_invoice")
            # The expand above is a request, not a guarantee: Stripe answers with the
            # bare id often enough that reading it like an object crashed the whole
            # subscribe call. Re-fetching rather than just skipping, because a None
            # client_secret leaves the frontend unable to confirm the card and the
            # subscription stuck as incomplete.
            if isinstance(latest_invoice, str):
                latest_invoice = stripe.Invoice.retrieve(
                    latest_invoice, expand=["confirmation_secret"]
                )
            subscription["client_secret"] = invoice_client_secret(latest_invoice)
            return subscription
        except Exception as e:
            logger.exception(e)
            raise SubscriptionCreationError("Error creating subscription intent in Stripe")

    def retrieve_subscription(
        self, subscription_id: str, **kwargs: Any
    ) -> "stripe.Subscription | None":
        try:
            subscription = stripe.Subscription.retrieve(subscription_id, **kwargs)
        except Exception as e:
            if "No such subscription" in str(e):
                return None
            logger.exception(e)
            raise SubscriptionNotFound("Error retrieving subscription in Stripe")
        # Expanded on some responses, so pass the id rather than the object to the
        # preview call below.
        customer = stripe_id(subscription.get("customer"))
        try:
            upcoming_invoice = self.get_upcoming_invoice(customer, subscription_id)
            subscription["upcoming_invoice"] = {
                "amount_due": upcoming_invoice.amount_due,
                "next_payment_attempt": upcoming_invoice.next_payment_attempt,
            }
        except InvoiceNotFound as e:
            # Narrow: get_upcoming_invoice raises only this, and a missing upcoming
            # invoice is the one failure worth tolerating here - anything else should
            # surface rather than leave the subscription silently short a field.
            # InvoiceNotFound only says the preview failed; __cause__ carries the Stripe
            # error that says why, which is the half worth logging.
            logger.warning(
                "Failed to retrieve upcoming invoice for customer %s: %s",
                customer,
                e.__cause__ or e,
            )
        return subscription

    def list_subscriptions(
        self, customer_id: str, **kwargs: Any
    ) -> "stripe.ListObject[stripe.Subscription]":
        try:
            # Stripe's default for an absent status is "everything not canceled", so
            # popping "all" returned the opposite of what it asks for - canceled
            # subscriptions could never come back.
            kwargs.setdefault("status", "active")
            subscriptions = stripe.Subscription.list(customer=customer_id, **kwargs)
            return subscriptions
        except Exception as e:
            if "No such customer" in str(e):
                return _empty_list_object("/v1/subscriptions")
            logger.exception(e)
            raise SubscriptionNotFound("Error retrieving subscriptions for customer in Stripe")

    def delete_subscription(self, subscription_id: str) -> "stripe.Subscription | None":
        try:
            response = stripe.Subscription.cancel(subscription_id)
            return response
        except Exception as e:
            if "No such subscription" in str(e):
                return None
            logger.exception(e)
            raise Exception("Error deleting subscription in Stripe")

    def list_products(self, **kwargs: Any) -> "list[stripe.Product]":
        try:
            if "active" not in kwargs:
                kwargs["active"] = True
            products = list(stripe.Product.list(**kwargs).auto_paging_iter())
            return products
        except Exception as e:
            logger.exception(e)
            raise Exception("Error retrieving products in Stripe")

    def retrieve_product(self, product_id: str) -> "stripe.Product | None":
        try:
            product = stripe.Product.retrieve(product_id, expand=["default_price"])
            return product
        except stripe.error.InvalidRequestError as e:
            logger.exception(f"Failed to retrieve product: {str(e)}")
            return None
        except stripe.error.StripeError as e:
            logger.exception(f"Stripe API error: {str(e)}")
            return None

    def retrieve_payment_method(self, payment_method_id: str) -> "stripe.PaymentMethod":
        try:
            payment_method = stripe.PaymentMethod.retrieve(payment_method_id)
            return payment_method
        except Exception as e:
            logger.exception(e)
            raise PaymentMethodNotFound("Error retrieving payment method in Stripe")

    def list_payment_methods(
        self, customer_id: str, type: str = "card"
    ) -> "stripe.ListObject[stripe.PaymentMethod]":
        try:
            payment_methods = stripe.PaymentMethod.list(
                customer=customer_id,
                type=type,
            )
            return payment_methods
        except stripe.InvalidRequestError as e:
            # Only a genuinely absent customer becomes CustomerNotFound. Translating
            # every exception here meant payment_method_belongs_to() answered False for
            # timeouts and outages, and the update/delete routes told the caller their
            # card did not exist while Stripe was simply unreachable.
            if getattr(e, "code", None) == "resource_missing":
                logger.warning("Customer %s not found in Stripe", customer_id)
                raise CustomerNotFound("Customer not found in Stripe") from e
            raise

    def get_customer_payment_methods(self, remote_customer_id: str) -> "list[stripe.PaymentMethod]":
        customer = self.retrieve_customer(remote_customer_id)
        if not customer:
            raise CustomerNotFound("Customer not found in Stripe")
        # Compared against pm.id below: if Stripe expands it, an object never matches
        # and no card is flagged as the default.
        default_payment_method = stripe_id(
            stripe_field(stripe_field(customer, "invoice_settings"), "default_payment_method")
        )
        try:
            # Materialized: the flag below is written onto each item and the whole
            # set is handed back for serialization.
            payment_methods = list(self.list_payment_methods(remote_customer_id).auto_paging_iter())
            if default_payment_method:
                for pm in payment_methods:
                    if pm.id == default_payment_method:
                        pm["is_default"] = True
                        break
            else:
                for pm in payment_methods:
                    pm["is_default"] = False
            return payment_methods
        except Exception as e:
            logger.exception(e)
            raise PaymentIntendNotFound("Failed to retrieve payment methods")

    def payment_method_belongs_to(
        self, payment_method_id: "str | None", customer_id: "str | None"
    ) -> bool:
        """Whether `payment_method_id` is attached to `customer_id`."""
        if not payment_method_id or not customer_id:
            return False
        try:
            payment_methods = self.list_payment_methods(customer_id)
        except CustomerNotFound:
            return False
        return any(pm["id"] == payment_method_id for pm in payment_methods.auto_paging_iter())

    def update_payment_method(
        self, payment_method_id: str, **kwargs: Any
    ) -> "stripe.PaymentMethod":
        try:
            return stripe.PaymentMethod.modify(
                payment_method_id,
                **kwargs,
            )
        except Exception as e:
            logger.exception(e)
            raise PaymentMethodUpdateError("Error updating payment method in Stripe")

    def delete_payment_method(
        self, payment_method_id: str, customer_id: str, is_default: bool = False
    ) -> "stripe.PaymentMethod":
        try:
            if is_default:
                stripe.Customer.modify(
                    customer_id, invoice_settings={"default_payment_method": None}
                )
            response = stripe.PaymentMethod.detach(payment_method_id)
            return response
        except Exception as e:
            logger.exception(e)
            raise PaymentMethodDeletionError("Error deleting payment method in Stripe")

    def get_payment_intent(self, payment_intent_id: str) -> "stripe.PaymentIntent | None":
        try:
            payment_intent = stripe.PaymentIntent.retrieve(payment_intent_id)
            return payment_intent
        except stripe.error.InvalidRequestError as e:
            if "No such PaymentIntent" in str(e):
                return None
            logger.exception(f"Failed to retrieve PaymentIntent: {str(e)}")
            raise PaymentIntendNotFound("Error retrieving PaymentIntent in Stripe")
        except Exception as e:
            logger.exception(e)
            raise PaymentIntendNotFound("Error retrieving PaymentIntent in Stripe")

    def create_setup_intent(self, customer_id: str) -> "stripe.SetupIntent":
        try:
            setup_intent = stripe.SetupIntent.create(
                customer=customer_id,
                payment_method_types=["card"],
            )
            return setup_intent
        except Exception as e:
            logger.exception(e)
            raise SetupIntentCreationError("Error creating SetupIntent in Stripe")

    def retrieve_price(self, price_id: str) -> "stripe.Price | None":
        try:
            price = stripe.Price.retrieve(price_id, expand=["product"])
            return price
        except stripe.error.InvalidRequestError as e:
            if "No such price" in str(e):
                logger.exception(f"Price not found: {price_id}")
                return None
            logger.exception(f"Invalid request for price {price_id}: {str(e)}")
            return None
        except stripe.error.StripeError as e:
            logger.exception(f"Stripe API error retrieving price {price_id}: {str(e)}")
            return None
        except Exception as e:
            logger.exception(f"Unexpected error retrieving price {price_id}: {str(e)}")
            raise PriceRetrievalError(f"Error retrieving price from Stripe: {str(e)}")

    def checkCustomerIdForUser(self, remote_customer_id: str, user: "AbstractBaseUser") -> bool:
        try:
            customer = self.retrieve_customer(remote_customer_id)
            if not customer:
                logger.warning(f"Customer {remote_customer_id} not found in Stripe.")
                return False
            linked_customer = Customer.objects.filter(
                remote_customer_id=remote_customer_id, entity_id=user.profile.id
            ).first()
            if linked_customer:
                return True
            else:
                logger.warning(
                    f"Customer {remote_customer_id} does not belong to user {user.profile.id}."
                )
                return False
        except Exception as e:
            logger.exception(f"Error checking customer ID for user: {e}")
            raise CustomerOwnershipError("Error verifying customer ownership.")

    def update_subscription(self, subscription_id: str, **kwargs: Any) -> "stripe.Subscription":
        try:
            subscription = stripe.Subscription.modify(subscription_id, **kwargs)
            return subscription
        except stripe.error.InvalidRequestError as e:
            if "No such subscription" in str(e):
                raise SubscriptionNotFound("Subscription not found in Stripe")
            logger.exception(f"Invalid request: {str(e)}")
            raise
        except Exception as e:
            logger.exception(e)
            raise SubscriptionCreationError("Error updating subscription in Stripe")

    def get_upcoming_invoice(
        self, customer_id: "str | None", subscription_id: "str | None" = None
    ) -> "stripe.Invoice":
        """Preview the customer's next invoice, optionally scoped to one subscription."""
        # stripe.Invoice.upcoming, which this used before, was dropped from the SDK;
        # create_preview is its replacement and the payments extra pins >=11.5,<15.
        params = {"customer": customer_id}
        if subscription_id:
            params["subscription"] = subscription_id
        try:
            return stripe.Invoice.create_preview(**params)
        except Exception as e:
            # Deliberately not logged here, unlike its neighbours: retrieve_subscription
            # treats a missing upcoming invoice as routine, and a canceled subscription
            # has none. `from e` keeps the cause for callers that do want to log it.
            raise InvoiceNotFound("Error retrieving upcoming invoice in Stripe") from e

    def list_invoices(self, customer_id: str) -> "stripe.ListObject[stripe.Invoice]":
        try:
            return stripe.Invoice.list(customer=customer_id)
        except Exception as e:
            logger.exception(e)
            raise InvoiceNotFound("Error retrieving invoices in Stripe")


# --- Card holds: the Stripe seam and readers -------------------------------------------
# Every card hold Stripe call goes through get_stripe(), so tests swap Stripe for a fake by
# patching that one function. Never log a card or billing object; ids only.

# Used only when Stripe reports no capture_before on the charge: a customer-initiated
# online authorization, and one placed off-session (Stripe's merchant-initiated window).
HOLD_EXPIRY_FALLBACK = datetime.timedelta(days=7)
OFF_SESSION_HOLD_EXPIRY_FALLBACK = datetime.timedelta(days=4, hours=18)
PAYMENT_INTENT_EXPAND = ["latest_charge", "payment_method"]
# No usable answer about the request, so it is retried with the same key: a connection
# error and a 429 (nothing cached for the key), and a 5xx (``APIError``), which Stripe
# does cache for the key and replays for 24 hours, so a retry may get the same 5xx.
RETRYABLE_STRIPE_ERRORS = (stripe.APIConnectionError, stripe.APIError, stripe.RateLimitError)
# A bad or revoked API key (401, 403): no answer about the card at all. Never a decline or
# a failed hold; the same request works once the key is fixed.
CONFIGURATION_STRIPE_ERRORS = (stripe.AuthenticationError, stripe.PermissionError)


def stripe_configured() -> bool:
    """Whether a Stripe secret key is set. Without one, card holds never call Stripe."""
    return bool(getattr(settings, "STRIPE_SECRET_KEY", ""))


def get_stripe() -> ModuleType:
    """The ``stripe`` module, configured the same way ``StripeService`` configures it."""
    configure_stripe()
    return stripe


@dataclass(frozen=True)
class Card:
    """The card fields recorded on a hold, read from a Stripe PaymentMethod."""

    payment_method_id: str
    brand: str = ""
    last4: str = ""
    exp_month: int = 0
    exp_year: int = 0
    funding: str = "unknown"
    fingerprint: str = ""


FUNDING_TYPES = ("credit", "debit", "prepaid", "unknown")


def normalize_funding(value: Any) -> str:
    """A Stripe card funding type, or ``unknown``."""
    return value if value in FUNDING_TYPES else "unknown"


def card_of(payment_method: Any) -> Card:
    """The card on an (expanded) PaymentMethod; an id string gives an empty card."""
    card = stripe_field(payment_method, "card")
    return Card(
        payment_method_id=stripe_id(payment_method) or "",
        brand=stripe_field(card, "brand", "") or "",
        last4=stripe_field(card, "last4", "") or "",
        exp_month=stripe_field(card, "exp_month", 0) or 0,
        exp_year=stripe_field(card, "exp_year", 0) or 0,
        funding=normalize_funding(stripe_field(card, "funding")),
        fingerprint=stripe_field(card, "fingerprint", "") or "",
    )


def is_idempotent_replay(stripe_object: Any) -> bool:
    """Whether Stripe answered with a cached response (``Idempotent-Replayed: true``).

    A replay reports the object as it was when first created, not as it is now.
    """
    response = getattr(stripe_object, "last_response", None)
    headers = getattr(response, "headers", None) or {}
    return any(
        name.lower() == "idempotent-replayed" and str(value).lower() == "true"
        for name, value in headers.items()
    )


def capture_before(payment_intent: Any) -> datetime.datetime | None:
    """When Stripe stops honouring the authorization, from the charge's ``capture_before``."""
    charge = stripe_field(payment_intent, "latest_charge")
    details = stripe_field(stripe_field(charge, "payment_method_details"), "card")
    epoch = stripe_field(details, "capture_before")
    if not epoch:
        return None
    return datetime.datetime.fromtimestamp(int(epoch), tz=datetime.timezone.utc)


def hold_expiry(
    payment_intent: Any, fallback: datetime.timedelta = HOLD_EXPIRY_FALLBACK
) -> datetime.datetime:
    """``capture_before``, or now + ``fallback`` (7 days by default; an off-session
    placement passes :data:`OFF_SESSION_HOLD_EXPIRY_FALLBACK`) with a warning when Stripe
    didn't send it."""
    expires_at = capture_before(payment_intent)
    if expires_at is None:
        logger.warning(
            "PaymentIntent %s has no capture_before; assuming a hold of %s",
            stripe_id(payment_intent),
            fallback,
        )
        return timezone.now() + fallback
    return expires_at


def payment_intent_status_of(
    error: stripe.InvalidRequestError, payment_intent_id: str
) -> str | None:
    """The PaymentIntent's status when Stripe refused a call only because of that status
    (``payment_intent_unexpected_state``), read from the error or else from Stripe;
    ``None`` for any other refusal."""
    if getattr(error, "code", None) != "payment_intent_unexpected_state":
        return None
    payment_intent = stripe_field(getattr(error, "error", None), "payment_intent")
    status = stripe_field(payment_intent, "status")
    if status is None:
        status = stripe_field(get_stripe().PaymentIntent.retrieve(payment_intent_id), "status")
    return status


def cancel_payment_intent_quietly(payment_intent_id: str) -> None:
    """Cancel a PaymentIntent once, logging instead of raising. Only for a PaymentIntent
    with no hold row; nothing retries it."""
    try:
        get_stripe().PaymentIntent.cancel(payment_intent_id)
    except stripe.StripeError:
        logger.warning("Could not cancel PaymentIntent %s", payment_intent_id, exc_info=True)
