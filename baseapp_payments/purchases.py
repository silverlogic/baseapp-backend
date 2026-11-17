"""One-time purchases: charge a customer once for one or more products by quantity.

A purchase is one Stripe invoice with an invoice item per product line. It never touches
the subscription flow. The browser confirms the invoice's payment with the
``confirmation_secret`` it gets back, which also completes 3D Secure. The purchase only
turns "paid" or "failed" when Stripe says so by webhook.

The feature is optional. It is on when the project sets both
``BASEAPP_PAYMENTS_PURCHASE_MODEL`` and ``BASEAPP_PAYMENTS_PURCHASELINE_MODEL``.
"""

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import stripe
import swapper
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .models import PurchaseStatus
from .signals import purchase_failed, purchase_paid
from .utils import StripeService, invoice_client_secret, stripe_field, stripe_id

if TYPE_CHECKING:
    from django.db.models import Model

    from .models import BaseCustomer, BasePurchase

logger = logging.getLogger(__name__)

# Upper bounds that keep a single request reasonable; Stripe allows 250 invoice items.
MAX_PURCHASE_LINES = 100
MAX_LINE_QUANTITY = 9999

# Statuses of an invoice's payment intent that are not a failure: the customer still has
# to act (3D Secure) or the payment is still settling.
PAYMENT_STILL_OPEN_STATUSES = frozenset({"requires_action", "requires_confirmation", "processing"})


def purchases_enabled() -> bool:
    """Whether the project opted into one-time purchases."""
    return bool(
        getattr(settings, "BASEAPP_PAYMENTS_PURCHASE_MODEL", None)
        and getattr(settings, "BASEAPP_PAYMENTS_PURCHASELINE_MODEL", None)
    )


def automatic_tax_enabled() -> bool:
    """Whether purchases ask Stripe Tax to add tax. Needs Stripe Tax active on the account."""
    return bool(getattr(settings, "BASEAPP_PAYMENTS_AUTOMATIC_TAX", False))


def get_purchase_model() -> "type[Model]":
    return swapper.load_model("baseapp_payments", "Purchase")


def get_purchase_line_model() -> "type[Model]":
    return swapper.load_model("baseapp_payments", "PurchaseLine")


class PurchaseValidationError(Exception):
    """The request asks for something that must not be charged. Nothing was sent to Stripe."""

    def __init__(self, field: str, message: str) -> None:
        super().__init__(message)
        self.field = field
        self.message = message


class PurchaseCreationError(Exception):
    """Stripe refused to create or finalize the invoice. Nothing was charged."""


@dataclass(frozen=True)
class ResolvedLine:
    """One product line, with the price read from Stripe rather than from the request."""

    product_id: str
    price_id: str
    description: str
    unit_amount: int
    quantity: int
    currency: str

    @property
    def amount(self) -> int:
        return self.unit_amount * self.quantity


def resolve_lines(items: "list[dict[str, Any]]", service: StripeService) -> "list[ResolvedLine]":
    """Turn ``[{product_id, quantity, unit_amount?}]`` into lines priced by Stripe.

    The server prices every line from the product's default price. An ``unit_amount``
    sent by the browser is only compared against it: a mismatch rejects the purchase.
    """
    if not items:
        raise PurchaseValidationError("items", _("At least one item is required."))
    if len(items) > MAX_PURCHASE_LINES:
        raise PurchaseValidationError(
            "items", _("A purchase can have at most %(max)s items.") % {"max": MAX_PURCHASE_LINES}
        )
    seen: set[str] = set()
    lines: list[ResolvedLine] = []
    for item in items:
        product_id = item["product_id"]
        quantity = item["quantity"]
        if product_id in seen:
            raise PurchaseValidationError(
                "items", _("Each product can appear only once; set its quantity instead.")
            )
        seen.add(product_id)
        # Serializer bounds already apply; repeated here because this is the last line
        # before Stripe, and callers other than the view can reach it.
        if not isinstance(quantity, int) or isinstance(quantity, bool) or quantity < 1:
            raise PurchaseValidationError(
                "items", _("Quantity must be a whole number of 1 or more.")
            )
        if quantity > MAX_LINE_QUANTITY:
            raise PurchaseValidationError(
                "items",
                _("Quantity can be at most %(max)s.") % {"max": MAX_LINE_QUANTITY},
            )
        product = service.retrieve_product(product_id)
        if not product or not stripe_field(product, "active"):
            raise PurchaseValidationError(
                "items", _("Product not available: %(id)s") % {"id": product_id}
            )
        price = stripe_field(product, "default_price")
        if isinstance(price, str):
            price = service.retrieve_price(price)
        if not price or not stripe_field(price, "active"):
            raise PurchaseValidationError(
                "items", _("Product has no price: %(id)s") % {"id": product_id}
            )
        # A recurring price belongs to the subscription flow; a one-time purchase must
        # not charge it, or the customer pays one period with no subscription behind it.
        if stripe_field(price, "type") != "one_time":
            raise PurchaseValidationError(
                "items",
                _("Product is not sold as a one-time purchase: %(id)s") % {"id": product_id},
            )
        unit_amount = stripe_field(price, "unit_amount")
        if unit_amount is None:
            raise PurchaseValidationError(
                "items", _("Product has no fixed price: %(id)s") % {"id": product_id}
            )
        sent_amount = item.get("unit_amount")
        if sent_amount is not None and sent_amount != unit_amount:
            raise PurchaseValidationError(
                "items",
                _("The price of %(id)s has changed. Review the order and try again.")
                % {"id": product_id},
            )
        lines.append(
            ResolvedLine(
                product_id=product_id,
                price_id=stripe_id(price),
                description=stripe_field(product, "name", "") or "",
                unit_amount=unit_amount,
                quantity=quantity,
                currency=stripe_field(price, "currency"),
            )
        )
    currencies = {line.currency for line in lines}
    if len(currencies) > 1:
        raise PurchaseValidationError(
            "items", _("All products in one purchase must use the same currency.")
        )
    return lines


def invoice_tax(invoice: Any) -> int:
    """The tax on a finalized invoice: total minus the total before tax."""
    total = stripe_field(invoice, "total") or 0
    excluding = stripe_field(invoice, "total_excluding_tax")
    return max(total - excluding, 0) if excluding is not None else 0


def create_purchase(
    customer: "BaseCustomer",
    items: "list[dict[str, Any]]",
    payment_method_id: "str | None" = None,
    service: "StripeService | None" = None,
) -> "tuple[BasePurchase, str | None]":
    """Create a pending purchase and its finalized Stripe invoice.

    Returns the purchase and the client secret the browser confirms the payment with.
    Nothing is charged here: the payment happens when the browser confirms it, and the
    purchase is marked paid or failed only by webhook.
    """
    service = service or StripeService()
    lines = resolve_lines(items, service)
    if payment_method_id and not service.payment_method_belongs_to(
        payment_method_id, customer.remote_customer_id
    ):
        raise PurchaseValidationError(
            "payment_method_id", _("The payment method does not belong to the customer.")
        )

    Purchase = get_purchase_model()
    PurchaseLine = get_purchase_line_model()
    subtotal = sum(line.amount for line in lines)
    currency = lines[0].currency
    with transaction.atomic():
        purchase = Purchase.objects.create(
            customer=customer,
            currency=currency,
            subtotal=subtotal,
            tax=0,
            total=subtotal,
        )
        PurchaseLine.objects.bulk_create(
            [
                PurchaseLine(
                    purchase=purchase,
                    remote_product_id=line.product_id,
                    remote_price_id=line.price_id,
                    description=line.description[:255],
                    unit_amount=line.unit_amount,
                    quantity=line.quantity,
                    amount=line.amount,
                )
                for line in lines
            ]
        )

    invoice_id = None
    try:
        invoice_params: dict[str, Any] = {
            "customer": customer.remote_customer_id,
            "currency": currency,
            "collection_method": "charge_automatically",
            # The browser confirms the payment; Stripe must not charge or retry on its own.
            "auto_advance": False,
            # Only this purchase's items, never pending items left on the customer.
            "pending_invoice_items_behavior": "exclude",
            "automatic_tax": {"enabled": automatic_tax_enabled()},
            "metadata": {"baseapp_purchase_id": str(purchase.pk)},
        }
        if payment_method_id:
            invoice_params["default_payment_method"] = payment_method_id
        invoice = stripe.Invoice.create(
            **invoice_params, idempotency_key=f"baseapp-purchase-{purchase.pk}-invoice"
        )
        invoice_id = stripe_id(invoice)
        for index, line in enumerate(lines):
            stripe.InvoiceItem.create(
                customer=customer.remote_customer_id,
                invoice=invoice_id,
                pricing={"price": line.price_id},
                quantity=line.quantity,
                idempotency_key=f"baseapp-purchase-{purchase.pk}-line-{index}",
            )
        invoice = stripe.Invoice.finalize_invoice(
            invoice_id, auto_advance=False, expand=["confirmation_secret"]
        )
        stripe_subtotal = stripe_field(invoice, "subtotal")
        if stripe_subtotal != subtotal:
            # The price changed between our read and Stripe's: charge nothing rather than
            # an amount the customer was not shown.
            raise PurchaseCreationError(
                f"Invoice subtotal {stripe_subtotal} differs from the quoted {subtotal}"
            )
    except (stripe.StripeError, PurchaseCreationError) as e:
        logger.exception("Failed to create the Stripe invoice for purchase %s", purchase.pk)
        if invoice_id:
            _void_quietly(invoice_id)
        purchase.delete()
        raise PurchaseCreationError("Error creating the purchase in Stripe") from e

    purchase.remote_invoice_id = invoice_id
    purchase.tax = invoice_tax(invoice)
    purchase.total = stripe_field(invoice, "total") or subtotal
    purchase.save(update_fields=["remote_invoice_id", "tax", "total", "modified"])
    return purchase, invoice_client_secret(invoice)


def _void_quietly(invoice_id: str) -> None:
    """Void an invoice so it can never be charged; failure only logs."""
    try:
        stripe.Invoice.void_invoice(invoice_id)
    except stripe.StripeError:
        logger.exception("Failed to void Stripe invoice %s", invoice_id)


def _invoice_payment_still_open(invoice_id: str) -> bool:
    """Whether the invoice's payment is waiting on the customer rather than failed."""
    try:
        invoice = stripe.Invoice.retrieve(
            invoice_id, expand=["payments.data.payment.payment_intent"]
        )
    except stripe.StripeError:
        logger.exception("Failed to read Stripe invoice %s", invoice_id)
        return False
    payments = stripe_field(stripe_field(invoice, "payments"), "data") or []
    for invoice_payment in payments:
        intent = stripe_field(stripe_field(invoice_payment, "payment"), "payment_intent")
        if stripe_field(intent, "status") in PAYMENT_STILL_OPEN_STATUSES:
            return True
    return False


def _transition(purchase_id: int, status: str, timestamp_field: str) -> bool:
    """Move a pending purchase to ``status`` once. True only for the call that moved it."""
    Purchase = get_purchase_model()
    updated = Purchase.objects.filter(pk=purchase_id, status=PurchaseStatus.PENDING).update(
        status=status, **{timestamp_field: timezone.now()}
    )
    return updated == 1


def handle_invoice_paid(invoice: Any) -> None:
    """``invoice.paid``: mark the purchase paid and fire ``purchase_paid`` once."""
    purchase = _purchase_for_invoice(invoice)
    if purchase is None:
        return
    if _transition(purchase.pk, PurchaseStatus.PAID, "paid_at"):
        purchase.refresh_from_db()
        transaction.on_commit(lambda: purchase_paid.send(sender=type(purchase), purchase=purchase))


def handle_invoice_payment_failed(invoice: Any) -> None:
    """``invoice.payment_failed``: mark the purchase failed and fire ``purchase_failed`` once.

    A payment that only needs 3D Secure is not a failure and is left pending. A real
    failure voids the invoice, so nothing can be charged on it later.
    """
    purchase = _purchase_for_invoice(invoice)
    if purchase is None or purchase.status != PurchaseStatus.PENDING:
        return
    if _invoice_payment_still_open(purchase.remote_invoice_id):
        return
    if _transition(purchase.pk, PurchaseStatus.FAILED, "failed_at"):
        _void_quietly(purchase.remote_invoice_id)
        purchase.refresh_from_db()
        transaction.on_commit(
            lambda: purchase_failed.send(sender=type(purchase), purchase=purchase)
        )


def _purchase_for_invoice(invoice: Any) -> "BasePurchase | None":
    """The purchase an invoice belongs to, or None for any other invoice (subscriptions)."""
    invoice_id = stripe_id(invoice)
    if not invoice_id:
        return None
    return get_purchase_model().objects.filter(remote_invoice_id=invoice_id).first()
