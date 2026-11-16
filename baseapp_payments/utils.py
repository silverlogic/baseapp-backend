import logging
from decimal import Decimal
from typing import TYPE_CHECKING, Any

import stripe
import swapper
from constance import config
from django.apps import apps
from django.conf import settings
from django.db import IntegrityError, transaction
from django.http import HttpRequest, JsonResponse

from baseapp_core.graphql import get_pk_from_relay_id

if TYPE_CHECKING:
    from django.contrib.auth.base_user import AbstractBaseUser

logger = logging.getLogger(__name__)

Customer = swapper.load_model("baseapp_payments", "Customer")
Subscription = swapper.load_model("baseapp_payments", "Subscription")


# The Stripe API version every request is made with. Kept equal to the version the pinned
# stripe library ships with (``stripe.api_version`` at import), and the version a project's
# webhook endpoint should be set to in the Stripe dashboard, so request and webhook
# payloads have the same shape. Overridable with the STRIPE_API_VERSION setting.
STRIPE_API_VERSION = "2026-10-28.endive"


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


def entity_pk_from_id(value: "str | int | None") -> "str | int | None":
    """The pk an ``entity_id`` names: a raw pk as is, a relay id decoded, else None.

    A purely numeric string is a raw pk and is never decoded. Some of them are also valid
    base64 (``"1400"``), and decoding one as a relay id yields a garbage pk instead of
    ``""``, which used to skip the raw-pk path and 404 a real customer. A relay id is base64
    of ``"Type:pk"`` and so is never all digits.
    """
    if value is None or value == "":
        return None
    if isinstance(value, int) or (isinstance(value, str) and value.isdigit()):
        return value
    try:
        return get_pk_from_relay_id(value) or None
    except (ValueError, TypeError):
        return None


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
    # Since stripe-python 15 a StripeObject is no longer a dict, so .get() is gone;
    # item access is what reads a field, and `in` is what tells a missing one apart.
    if isinstance(obj, stripe.StripeObject):
        return obj[field] if field in obj else default
    return getattr(obj, field, default)


def stripe_dict(obj: Any) -> Any:
    """``obj`` as plain dicts and lists, all the way down.

    Since stripe-python 15 a StripeObject is no longer a dict: DRF fields such as
    ``DictField`` and the JSON renderer cannot read it, and ``isinstance(x, dict)``
    checks stop matching. Converting once at the boundary keeps every reader working.
    Anything that is not a StripeObject is returned unchanged.
    """
    if isinstance(obj, stripe.StripeObject):
        return obj.to_dict()
    return obj


def stripe_id(value: "stripe.StripeObject | dict[str, Any] | str | None") -> "str | None":
    """The id of an expandable field, whichever shape Stripe sent."""
    if value is None or isinstance(value, str):
        return value
    return stripe_field(value, "id")


def invoice_client_secret(invoice: "stripe.Invoice | dict[str, Any] | str | None") -> "str | None":
    """The client secret that confirms ``invoice``'s payment, when it was expanded.

    Since API 2025-03-31.basil this is ``invoice.confirmation_secret.client_secret``;
    the invoice no longer links a payment intent. None when the invoice arrived as a
    bare id or without ``confirmation_secret`` expanded.
    """
    return stripe_field(stripe_field(invoice, "confirmation_secret"), "client_secret")


# Line-item parent types since API 2025-03-31.basil, mapped back to the `type` values the
# line's own field used to carry.
INVOICE_LINE_PARENT_TYPES = {
    "subscription_item_details": "subscription",
    "invoice_item_details": "invoiceitem",
}


def invoice_line_legacy_fields(line: "dict[str, Any]") -> "dict[str, Any]":
    """``type`` and ``price`` for an invoice line, read from where API basil moved them.

    Basil replaced the line's top-level ``type`` with ``parent.type`` and its ``price``
    with ``pricing.price_details.price`` - an id, since a line list cannot expand that
    deep. Without this both fields silently dropped out of the invoices response. The
    price is rebuilt from the line's own currency and unit amount; ``recurring`` is not
    on the line, so it is None. A line still in the old shape is returned as is.
    """
    parent_type = stripe_field(stripe_field(line, "parent"), "type")
    line_type = INVOICE_LINE_PARENT_TYPES.get(parent_type, parent_type) or line.get("type")
    price = line.get("price")
    pricing = stripe_field(line, "pricing")
    details_price = stripe_field(stripe_field(pricing, "price_details"), "price")
    if price is None and isinstance(details_price, dict):
        price = details_price
    elif price is None and details_price:
        unit_amount_decimal = stripe_field(pricing, "unit_amount_decimal")
        amount = Decimal(str(unit_amount_decimal)) if unit_amount_decimal is not None else None
        price = {
            "id": details_price,
            "currency": line.get("currency"),
            # unit_amount is a whole number of the currency's minor unit; a sub-cent decimal
            # price has no integer form, so it is None rather than truncated.
            "unit_amount": (
                int(amount) if amount is not None and amount == amount.to_integral_value() else None
            ),
            "recurring": None,
        }
    return {"type": line_type, "price": price}


def subscription_period_end(subscription: "stripe.Subscription | dict[str, Any]") -> "int | None":
    """When the subscription's current billing period ends, as a Unix timestamp.

    Since API 2025-03-31.basil the period is set per subscription item, not on the
    subscription. With one price per subscription, as this module creates them, the
    first item's period is the subscription's.
    """
    items = stripe_field(stripe_field(subscription, "items"), "data") or []
    if not items:
        return None
    return stripe_field(items[0], "current_period_end")


def _empty_list_object(url: str) -> "stripe.ListObject":
    """An empty Stripe ``ListObject``.

    Callers page over every ``list_*`` result, so a "nothing found" answer has to
    support ``auto_paging_iter()`` too - a bare ``[]`` would raise instead.
    """
    return stripe.ListObject.construct_from(
        {"object": "list", "data": [], "has_more": False, "url": url}, stripe.api_key
    )


class StripeWebhookHandler:
    def __init__(self) -> None:
        self.EVENT_HANDLERS = {
            "customer.created": self.customer_created,
            "customer.deleted": self.customer_deleted,
            "customer.subscription.created": self.subscription_created,
            "customer.subscription.deleted": self.subscription_deleted,
        }

    @staticmethod
    def customer_created(event: "stripe.Event") -> JsonResponse:
        customer_data = event["data"]["object"]
        try:
            existing_customer = Customer.objects.filter(
                remote_customer_id=customer_data["id"]
            ).first()
            if existing_customer:
                return JsonResponse({"status": "success"}, status=200)
            entity_id = stripe_field(customer_data["metadata"], "entity_id")
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


class StripeService:
    def __init__(
        self,
        api_key: str = settings.STRIPE_SECRET_KEY,
        api_version: str = getattr(settings, "STRIPE_API_VERSION", STRIPE_API_VERSION),
    ) -> None:
        stripe.api_key = api_key
        stripe.api_version = api_version

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

    def create_subscription(
        self, customer_id: str, price_id: str, payment_method_id: "str | None" = None
    ) -> "stripe.Subscription":
        """Create and charge a subscription right away.

        ``payment_method_id`` becomes the subscription's default card; without it Stripe
        charges the customer's default. The serializer passes it whenever the caller chose
        a card, and this signature not accepting it made every such request a 400.
        """
        params: dict[str, Any] = {"customer": customer_id, "items": [{"price": price_id}]}
        if payment_method_id:
            params["default_payment_method"] = payment_method_id
        try:
            subscription = stripe.Subscription.create(**params)
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
                # Since API 2025-03-31.basil an invoice no longer links its payment
                # intent; the secret the frontend confirms the first payment with is
                # the invoice's confirmation_secret, which is only sent when expanded.
                expand=["latest_invoice.confirmation_secret"],
                metadata={"product_id": product_id} if product_id else None,
            )
            latest_invoice = stripe_field(subscription, "latest_invoice")
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
        customer = stripe_id(stripe_field(subscription, "customer"))
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
                # payment_method_types is rejected with a 400 since API 2026-09-30.endive;
                # this is its replacement and keeps saving to cards only.
                allowed_payment_method_types=["card"],
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
        # create_preview replaced the Upcoming Invoice API, removed in API 2025-03-31.basil.
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
