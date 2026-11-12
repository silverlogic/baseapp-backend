"""An in-memory stand-in for the parts of the Stripe API card holds use.

Every card hold Stripe call goes through ``baseapp_payments.utils.get_stripe``, so tests patch that one function with a :class:`FakeStripe` (the
``fake_stripe`` fixture). It keeps PaymentMethods, PaymentIntents and SetupIntents as
Stripe would, honours idempotency keys the way Stripe does (a repeat with the same
parameters replays the first answer with ``Idempotent-Replayed: true``; different
parameters raise ``IdempotencyError``), and records every call so a test can assert what
was, and wasn't, sent. It is thread-safe, for the concurrency tests.

Errors are built as stripe-python builds them from Stripe's responses
(``_api_requestor.specific_v1_api_error``): a 409 is an ``APIError``, an
``idempotency_error`` an ``IdempotencyError`` (not an ``InvalidRequestError``), a 429 a
``RateLimitError``. :meth:`FakeStripe.lapse` models an authorization that expired.

Off-session placement (``off_session=True``): ``next_outcome`` entries
``"authentication_required"`` and ``"insufficient_funds"`` raise the ``CardError``
Stripe raises for those, with the failed PaymentIntent attached. SetupIntents (saving a
card for later) honour idempotency keys the same way, end in ``next_setup_outcome``
(default ``succeeded``) and attach the card to the customer when they succeed.

Lost answers and reconciliation: :meth:`FakeStripe.fail_behind_next` makes the next
PaymentIntent creation create its PaymentIntent and still answer with an error (a 5xx
Stripe saves for the key); :meth:`FakeStripe.prune_keys` forgets idempotency keys, as
Stripe does after 24 hours, so a replay runs as a fresh request. ``PaymentIntent.search``
and ``PaymentIntent.list`` find PaymentIntents by metadata and by customer;
:func:`deliver_event` posts a signed webhook event to the real endpoint.

Basil (API 2025-03-31.basil and later): an automatic-capture PaymentIntent confirmed at
create (the difference above a hold, a project's charge) ends ``succeeded``; every
captured payment's ``latest_charge`` carries a balance transaction with Stripe's fee
(expanded only when ``latest_charge.balance_transaction`` is asked for; ``None`` while
``balance_ready`` is off, as when Stripe hasn't made it yet); a PaymentIntent Stripe
cancels when its authorization lapses says ``cancellation_reason="expired"``; and
invoices take several payments (``Invoice.attach_payment``, ``invoice.payments``,
``InvoicePayment.list`` paged by ``invoice_page_size``).
"""

import copy
import hashlib
import hmac
import itertools
import json
import re
import threading
import time
from collections.abc import Callable
from typing import Any

import stripe
from stripe._stripe_response import StripeResponse

TEST_KEY = "sk_test_card_holds"
STRIPE_CUSTOMER_ID = "cus_holder"
# 2030-03-17: a capture_before comfortably in the future.
CAPTURE_BEFORE = 1_900_000_000


# --- Error builders ---------------------------------------------------------------------


def card_declined(
    payment_intent_id: str | None = None,
    *,
    code: str = "card_declined",
    decline_code: str | None = None,
) -> stripe.CardError:
    """A decline; Stripe sends the failed PaymentIntent along when it created one. An
    off-session payment the bank wants authenticated is ``authentication_required``."""
    error: dict[str, Any] = {"code": code, "type": "card_error"}
    if decline_code is not None:
        error["decline_code"] = decline_code
    if payment_intent_id is not None:
        error["payment_intent"] = {
            "id": payment_intent_id,
            "object": "payment_intent",
            "status": "requires_payment_method",
        }
    return stripe.CardError(
        "Your card was declined.",
        None,
        code,
        http_status=402,
        json_body={"error": error},
    )


# next_outcome entries that end a PaymentIntent creation in a CardError.
CARD_ERRORS = {
    "card_declined": {"code": "card_declined"},
    "authentication_required": {"code": "authentication_required"},
    "insufficient_funds": {"code": "card_declined", "decline_code": "insufficient_funds"},
}


def idempotency_error() -> stripe.IdempotencyError:
    """Stripe's 400 ``idempotency_error``; stripe-python sets no ``code`` on it."""
    message = "Keys for idempotent requests can only be used with the same parameters."
    return stripe.IdempotencyError(
        message,
        http_status=400,
        json_body={"error": {"type": "idempotency_error", "message": message}},
    )


def concurrent_request() -> stripe.APIError:
    """Stripe's 409: another request with the same idempotency key is still running.
    stripe-python maps any status it has no class for (409 included) to ``APIError``."""
    message = "There is currently another in-progress request using this Stripe-Idempotency-Key."
    return stripe.APIError(
        message,
        http_status=409,
        json_body={
            "error": {
                "type": "idempotency_error",
                "code": "idempotency_key_in_use",
                "message": message,
            }
        },
    )


def rate_limited() -> stripe.RateLimitError:
    return stripe.RateLimitError("Too many requests hit the API too quickly.", http_status=429)


def charge_expired() -> stripe.InvalidRequestError:
    """A capture of an authorization that lapsed before Stripe cancelled it."""
    return stripe.InvalidRequestError(
        "This PaymentIntent could not be captured because it has expired.",
        None,
        code="charge_expired_for_capture",
        http_status=400,
    )


def _cached_by_stripe(error: Exception) -> bool:
    """Whether Stripe saves this answer for the idempotency key: not when no response
    came, nor for a 409, a 429, or a key it refuses (401, 403), all rejected before the
    request runs."""
    if isinstance(
        error,
        (
            stripe.APIConnectionError,
            stripe.RateLimitError,
            stripe.AuthenticationError,
            stripe.PermissionError,
        ),
    ):
        return False
    return getattr(error, "http_status", None) != 409


def connection_error() -> stripe.APIConnectionError:
    return stripe.APIConnectionError("Network error communicating with Stripe.")


def api_error() -> stripe.APIError:
    return stripe.APIError("Stripe had a problem.", http_status=500)


def resource_missing(kind: str, object_id: str) -> stripe.InvalidRequestError:
    return stripe.InvalidRequestError(
        f"No such {kind}: '{object_id}'", "id", code="resource_missing", http_status=404
    )


def unexpected_state(
    payment_intent_id: str, status: str, action: str, *, with_intent: bool = True
) -> stripe.InvalidRequestError:
    error: dict[str, Any] = {"code": "payment_intent_unexpected_state"}
    if with_intent:
        error["payment_intent"] = {
            "id": payment_intent_id,
            "object": "payment_intent",
            "status": status,
        }
    return stripe.InvalidRequestError(
        f"You cannot {action} this PaymentIntent because it has a status of {status}.",
        None,
        code="payment_intent_unexpected_state",
        http_status=400,
        json_body={"error": error},
    )


# --- Objects ----------------------------------------------------------------------------


def payment_method_data(
    pm_id: str = "pm_visa",
    *,
    customer: str | None = STRIPE_CUSTOMER_ID,
    brand: str = "visa",
    last4: str = "4242",
    funding: str = "credit",
    exp_month: int = 8,
    exp_year: int = 2099,
    type: str = "card",
    fingerprint: str = "fp_visa",
) -> dict[str, Any]:
    return {
        "id": pm_id,
        "object": "payment_method",
        "type": type,
        "customer": customer,
        "created": 1_700_000_000,
        "card": {
            "brand": brand,
            "last4": last4,
            "funding": funding,
            "exp_month": exp_month,
            "exp_year": exp_year,
            "fingerprint": fingerprint,
        },
    }


class _Api:
    def __init__(self, fake: "FakeStripe") -> None:
        self.fake = fake


class _PaymentMethodApi(_Api):
    def retrieve(self, payment_method_id: str, **params: Any) -> stripe.PaymentMethod:
        self.fake.record("PaymentMethod.retrieve", payment_method_id, **params)
        self.fake.raise_queued("PaymentMethod.retrieve")
        data = self.fake.payment_methods.get(payment_method_id)
        if data is None:
            raise resource_missing("payment_method", payment_method_id)
        return stripe.PaymentMethod.construct_from(copy.deepcopy(data), TEST_KEY)


class _PaymentIntentApi(_Api):
    """Manual-capture PaymentIntents, by id, with their status and amount."""

    def create(self, **params: Any) -> stripe.PaymentIntent:
        self.fake.record("PaymentIntent.create", **params)
        key = params.get("idempotency_key")
        with self.fake.lock:
            if key is not None and key in self.fake.replies:
                first_params, reply = self.fake.replies[key]
                if _comparable(first_params) != _comparable(params):
                    raise idempotency_error()
                if isinstance(reply, Exception):
                    raise reply
                return self._construct(reply, replayed=True, expand=params.get("expand"))
            if key is not None and key in self.fake.in_flight:
                raise concurrent_request()
            if key is not None:
                self.fake.in_flight.add(key)
        try:
            return self._create(params, key)
        finally:
            with self.fake.lock:
                self.fake.in_flight.discard(key)

    def _create(self, params: dict[str, Any], key: str | None) -> stripe.PaymentIntent:
        if self.fake.before_create is not None:
            self.fake.before_create(params)
        try:
            self.fake.raise_queued("PaymentIntent.create")
            payment_intent_id = f"pi_{next(self.fake.ids)}"
            outcome = self.fake.next_outcome.pop(0) if self.fake.next_outcome else None
            automatic = params.get("capture_method", "automatic") != "manual"
            status = outcome or (
                "succeeded" if automatic and params.get("confirm") else "requires_capture"
            )
            if status in CARD_ERRORS:
                with self.fake.lock:
                    self.fake.intents[payment_intent_id] = self._data(
                        payment_intent_id, params, "requires_payment_method"
                    )
                raise card_declined(payment_intent_id, **CARD_ERRORS[status])
            with self.fake.lock:
                behind = self.fake.behind_errors.pop(0) if self.fake.behind_errors else None
            if behind is not None:
                # Created, but the answer is lost: the error is what the caller sees.
                with self.fake.lock:
                    self.fake.intents[payment_intent_id] = self._data(
                        payment_intent_id, params, status
                    )
                raise behind
        except stripe.StripeError as error:
            if key and _cached_by_stripe(error):
                with self.fake.lock:
                    self.fake.replies[key] = (params, error)
            raise
        with self.fake.lock:
            self.fake.intents[payment_intent_id] = self._data(payment_intent_id, params, status)
            if key:
                self.fake.replies[key] = (params, payment_intent_id)
        return self._construct(payment_intent_id, expand=params.get("expand"))

    def _data(self, payment_intent_id: str, params: dict[str, Any], status: str) -> dict:
        return {
            "id": payment_intent_id,
            "object": "payment_intent",
            "status": status,
            "capture_method": params.get("capture_method", "automatic"),
            "amount": params["amount"],
            "currency": params.get("currency", "usd"),
            "customer": params.get("customer"),
            "metadata": dict(params.get("metadata") or {}),
            "payment_method": params.get("payment_method"),
            "client_secret": f"{payment_intent_id}_secret",
            "capture_before": self.fake.capture_before,
            "amount_received": params["amount"] if status == "succeeded" else 0,
            "created": int(time.time()),
        }

    def _construct(
        self,
        payment_intent_id: str,
        *,
        replayed: bool = False,
        expand: list[str] | None = None,
    ) -> Any:
        with self.fake.lock:
            data = copy.deepcopy(self.fake.intents[payment_intent_id])
        payment_method_id = data.pop("payment_method")
        capture_before = data.pop("capture_before")
        data.pop("lapsed", None)
        data["payment_method"] = copy.deepcopy(
            self.fake.payment_methods.get(payment_method_id, payment_method_id)
        )
        data["latest_charge"] = {
            "id": f"ch_{payment_intent_id}",
            "object": "charge",
            "payment_method_details": {
                "card": {"capture_before": capture_before} if capture_before else {}
            },
            "balance_transaction": self.fake.balance_transaction(
                data, expanded="latest_charge.balance_transaction" in (expand or [])
            ),
        }
        data["amount_capturable"] = data["amount"] if data["status"] == "requires_capture" else 0
        return stripe.PaymentIntent.construct_from(
            data,
            TEST_KEY,
            last_response=(
                StripeResponse("{}", 200, {"Idempotent-Replayed": "true"}) if replayed else None
            ),
        )

    def search(self, *, query: str, **params: Any) -> stripe.SearchResultObject:
        """Stripe's Search, for ``metadata['key']:'value'`` queries only (no lag here)."""
        self.fake.record("PaymentIntent.search", query=query, **params)
        self.fake.raise_queued("PaymentIntent.search")
        match = re.fullmatch(r"metadata\['(\w+)'\]:'([^']*)'", query)
        if match is None:
            raise stripe.InvalidRequestError(f"Unsupported query: {query}", "query")
        field, value = match.groups()
        with self.fake.lock:
            found = [
                pid
                for pid, data in self.fake.intents.items()
                if data["metadata"].get(field) == value
            ]
        return stripe.SearchResultObject.construct_from(
            {
                "object": "search_result",
                "data": [self._construct(pid) for pid in found],
                "has_more": False,
                "url": "/v1/payment_intents/search",
            },
            TEST_KEY,
        )

    def list(self, **params: Any) -> stripe.ListObject:
        """The customer's PaymentIntents, created at or after ``created['gte']``."""
        self.fake.record("PaymentIntent.list", **params)
        self.fake.raise_queued("PaymentIntent.list")
        since = (params.get("created") or {}).get("gte", 0)
        with self.fake.lock:
            found = [
                pid
                for pid, data in self.fake.intents.items()
                if data["customer"] == params.get("customer") and data["created"] >= since
            ]
        return stripe.ListObject.construct_from(
            {
                "object": "list",
                "data": [self._construct(pid) for pid in found],
                "has_more": False,
                "url": "/v1/payment_intents",
            },
            TEST_KEY,
        )

    def retrieve(self, payment_intent_id: str, **params: Any) -> stripe.PaymentIntent:
        self.fake.record("PaymentIntent.retrieve", payment_intent_id, **params)
        if self.fake.before_retrieve is not None:
            self.fake.before_retrieve(payment_intent_id)
        self.fake.raise_queued("PaymentIntent.retrieve")
        if payment_intent_id not in self.fake.intents:
            raise resource_missing("payment_intent", payment_intent_id)
        return self._construct(payment_intent_id, expand=params.get("expand"))

    def cancel(self, payment_intent_id: str, **params: Any) -> stripe.PaymentIntent:
        self.fake.record("PaymentIntent.cancel", payment_intent_id, **params)
        self.fake.raise_queued("PaymentIntent.cancel")
        with self.fake.lock:
            data = self.fake.intents.get(payment_intent_id)
            if data is None:
                raise resource_missing("payment_intent", payment_intent_id)
            if data["status"] in ("canceled", "succeeded"):
                raise unexpected_state(payment_intent_id, data["status"], "cancel")
            data["status"] = "canceled"
        return self._construct(payment_intent_id)

    def capture(self, payment_intent_id: str, **params: Any) -> stripe.PaymentIntent:
        """Captures ``amount_to_capture`` (at most the amount capturable) once; a repeated
        idempotency key replays the first answer, as Stripe does for 24 hours."""
        self.fake.record("PaymentIntent.capture", payment_intent_id, **params)
        key = params.get("idempotency_key")
        request = {**params, "payment_intent": payment_intent_id}
        with self.fake.lock:
            if key in self.fake.replies:
                first_request, reply = self.fake.replies[key]
                # As Stripe: a key reused for another PaymentIntent or other parameters.
                if _comparable(first_request) != _comparable(request):
                    raise idempotency_error()
                if isinstance(reply, Exception):
                    raise reply
                return self._construct(reply, replayed=True, expand=params.get("expand"))
        try:
            self.fake.raise_queued("PaymentIntent.capture")
            data = self.fake.intents.get(payment_intent_id)
            if data is None:
                raise resource_missing("payment_intent", payment_intent_id)
            if data["status"] != "requires_capture":
                raise unexpected_state(payment_intent_id, data["status"], "capture")
            if data.get("lapsed"):
                raise charge_expired()
            amount = params.get("amount_to_capture", data["amount"])
            if amount > data["amount"]:
                raise stripe.InvalidRequestError(
                    "The amount to capture must be at most the amount capturable.",
                    "amount_to_capture",
                    code="amount_too_large",
                )
        except stripe.StripeError as error:
            if key and _cached_by_stripe(error):
                self.fake.replies[key] = (request, error)
            raise
        with self.fake.lock:
            data["status"] = "succeeded"
            data["amount_received"] = amount
            self.fake.captures.append((payment_intent_id, amount))
            if key:
                self.fake.replies[key] = (request, payment_intent_id)
        return self._construct(payment_intent_id, expand=params.get("expand"))


class _SetupIntentApi(_Api):
    """SetupIntents: saving a card for later, without the customer present."""

    def create(self, **params: Any) -> stripe.SetupIntent:
        self.fake.record("SetupIntent.create", **params)
        key = params.get("idempotency_key")
        with self.fake.lock:
            if key is not None and key in self.fake.replies:
                first_params, reply = self.fake.replies[key]
                if _comparable(first_params) != _comparable(params):
                    raise idempotency_error()
                if isinstance(reply, Exception):
                    raise reply
                return self._construct(reply, replayed=True)
        try:
            self.fake.raise_queued("SetupIntent.create")
            setup_intent_id = f"seti_{next(self.fake.ids)}"
            status = (
                self.fake.next_setup_outcome.pop(0) if self.fake.next_setup_outcome else "succeeded"
            )
            if status == "card_declined":
                raise card_declined()
        except stripe.StripeError as error:
            if key and _cached_by_stripe(error):
                with self.fake.lock:
                    self.fake.replies[key] = (params, error)
            raise
        with self.fake.lock:
            self.fake.setup_intents[setup_intent_id] = {
                "id": setup_intent_id,
                "object": "setup_intent",
                "status": status,
                "customer": params.get("customer"),
                "payment_method": params.get("payment_method"),
                "usage": params.get("usage", "off_session"),
                "metadata": dict(params.get("metadata") or {}),
                "client_secret": f"{setup_intent_id}_secret",
            }
            if key:
                self.fake.replies[key] = (params, setup_intent_id)
        if status == "succeeded":
            self.fake.attach(setup_intent_id)
        return self._construct(setup_intent_id)

    def _construct(self, setup_intent_id: str, *, replayed: bool = False) -> Any:
        with self.fake.lock:
            data = copy.deepcopy(self.fake.setup_intents[setup_intent_id])
        payment_method_id = data.pop("payment_method")
        data["payment_method"] = copy.deepcopy(
            self.fake.payment_methods.get(payment_method_id, payment_method_id)
        )
        return stripe.SetupIntent.construct_from(
            data,
            TEST_KEY,
            last_response=(
                StripeResponse("{}", 200, {"Idempotent-Replayed": "true"}) if replayed else None
            ),
        )

    def retrieve(self, setup_intent_id: str, **params: Any) -> stripe.SetupIntent:
        self.fake.record("SetupIntent.retrieve", setup_intent_id, **params)
        self.fake.raise_queued("SetupIntent.retrieve")
        if setup_intent_id not in self.fake.setup_intents:
            raise resource_missing("setup_intent", setup_intent_id)
        return self._construct(setup_intent_id)


class _InvoiceApi(_Api):
    """Invoices that take several payments (basil): ``retrieve`` (``payments`` listed)
    and ``attach_payment``, which credits a succeeded PaymentIntent at once."""

    def retrieve(self, invoice_id: str, **params: Any) -> stripe.Invoice:
        self.fake.record("Invoice.retrieve", invoice_id, **params)
        self.fake.raise_queued("Invoice.retrieve")
        if invoice_id not in self.fake.invoices:
            raise resource_missing("invoice", invoice_id)
        return self._construct(invoice_id)

    def attach_payment(self, invoice_id: str, **params: Any) -> stripe.Invoice:
        """Stripe's rules, as far as card holds meet them: the invoice must be open, the
        PaymentIntent the invoice's customer's and currency's, not on it already, and no
        larger than what remains due."""
        self.fake.record("Invoice.attach_payment", invoice_id, **params)
        key = params.get("idempotency_key")
        with self.fake.lock:
            if key is not None and key in self.fake.replies:
                first_params, reply = self.fake.replies[key]
                if _comparable(first_params) != _comparable(params):
                    raise idempotency_error()
                return self._construct(reply)
        self.fake.raise_queued("Invoice.attach_payment")
        payment_intent_id = params["payment_intent"]
        with self.fake.lock:
            invoice = self.fake.invoices.get(invoice_id)
            intent = self.fake.intents.get(payment_intent_id)
            if invoice is None:
                raise resource_missing("invoice", invoice_id)
            if intent is None:
                raise resource_missing("payment_intent", payment_intent_id)
            if invoice["status"] != "open":
                raise stripe.InvalidRequestError("This invoice isn't open.", None)
            if payment_intent_id in invoice["attached"]:
                raise stripe.InvalidRequestError("Already attached to this invoice.", None)
            if (
                intent.get("customer") != invoice["customer"]
                or intent.get("currency", "usd") != invoice["currency"]
            ):
                raise stripe.InvalidRequestError("Customer or currency mismatch.", None)
            amount = intent["amount_received"] or intent["amount"]
            if amount > invoice["amount_remaining"]:
                raise stripe.InvalidRequestError("More than the amount remaining.", None)
            invoice["attached"].append(payment_intent_id)
            if intent["status"] == "succeeded":
                invoice["amount_paid"] += amount
                invoice["amount_remaining"] -= amount
                if invoice["amount_remaining"] == 0:
                    invoice["status"] = "paid"
            if key is not None:
                self.fake.replies[key] = (params, invoice_id)
        return self._construct(invoice_id)

    def _construct(self, invoice_id: str) -> stripe.Invoice:
        with self.fake.lock:
            data = copy.deepcopy(self.fake.invoices[invoice_id])
        attached = data.pop("attached")
        data["payments"] = {
            "object": "list",
            "data": [
                {
                    "object": "invoice_payment",
                    "invoice": invoice_id,
                    "payment": {"type": "payment_intent", "payment_intent": pid},
                    "status": "paid" if self.fake.status_of(pid) == "succeeded" else "open",
                }
                for pid in attached
            ],
            "has_more": False,
        }
        return stripe.Invoice.construct_from(data, TEST_KEY)


class _Pages:
    """A Stripe list read page by page: ``data`` is the first page, and
    ``auto_paging_iter`` fetches the rest (each page recorded as a call)."""

    def __init__(self, fake: "FakeStripe", name: str, items: list[Any], size: int) -> None:
        self.fake = fake
        self.name = name
        self.items = items
        self.size = size
        self.data = items[:size]

    def auto_paging_iter(self) -> Any:
        yield from self.data
        for start in range(self.size, len(self.items), self.size):
            self.fake.record(self.name, starting_after=self.items[start - 1]["id"])
            yield from self.items[start : start + self.size]


class _InvoicePaymentApi(_Api):
    """``InvoicePayment.list(invoice=...)``: the payments on an invoice, every page."""

    def list(self, **params: Any) -> _Pages:
        self.fake.record("InvoicePayment.list", **params)
        self.fake.raise_queued("InvoicePayment.list")
        invoice_id = params.get("invoice")
        with self.fake.lock:
            if invoice_id not in self.fake.invoices:
                raise resource_missing("invoice", invoice_id)
            attached = list(self.fake.invoices[invoice_id]["attached"])
        items = [
            {
                "id": f"inpay_{invoice_id}_{pid}",
                "object": "invoice_payment",
                "invoice": invoice_id,
                "payment": {"type": "payment_intent", "payment_intent": pid},
                "status": "paid" if self.fake.status_of(pid) == "succeeded" else "open",
            }
            for pid in attached
        ]
        size = min(params.get("limit", 10), self.fake.invoice_page_size)
        return _Pages(self.fake, "InvoicePayment.list", items, size)


def project_charge(
    fake: "FakeStripe", *, payment_method: str = "pm_visa", amount: int = 10_000
) -> Callable[..., Any]:
    """A project's ``charge`` callable for :func:`capture`: one automatic-capture,
    off-session PaymentIntent with the key it is handed, so the fake's idempotency rules
    apply (a decline from ``next_outcome`` is saved for the key and replayed; the same key
    with another card raises ``IdempotencyError``)."""

    def charge(*, idempotency_key: str) -> stripe.PaymentIntent:
        return fake.PaymentIntent.create(
            amount=amount,
            currency="usd",
            customer=STRIPE_CUSTOMER_ID,
            payment_method=payment_method,
            confirm=True,
            off_session=True,
            idempotency_key=idempotency_key,
        )

    return charge


def _comparable(params: dict[str, Any]) -> dict[str, Any]:
    """The parameters Stripe compares for an idempotent replay (not the key itself)."""
    return {key: value for key, value in params.items() if key not in ("idempotency_key",)}


class FakeStripe:
    """The ``stripe`` module as far as card holds use it."""

    # Exception classes, so ``fake.CardError`` etc. still work for code that reads them.
    StripeError = stripe.StripeError
    CardError = stripe.CardError
    InvalidRequestError = stripe.InvalidRequestError

    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.ids = itertools.count(1)
        self.calls: list[tuple[str, tuple, dict]] = []
        self.errors: dict[str, list[Exception]] = {}
        self.payment_methods: dict[str, dict[str, Any]] = {}
        self.intents: dict[str, dict[str, Any]] = {}
        self.setup_intents: dict[str, dict[str, Any]] = {}
        # Idempotency key → (first params, PaymentIntent id or the error first raised).
        self.replies: dict[str, tuple[dict[str, Any], Any]] = {}
        # Keys of creations still running: a concurrent repeat is Stripe's 409.
        self.in_flight: set[str] = set()
        # Statuses the next PaymentIntent creations end in ("requires_action",
        # "card_declined", "requires_payment_method", ...); default "requires_capture".
        self.next_outcome: list[str] = []
        # Statuses the next SetupIntent creations end in ("requires_action",
        # "requires_payment_method", "processing", "card_declined"); default "succeeded".
        self.next_setup_outcome: list[str] = []
        self.capture_before: int | None = CAPTURE_BEFORE
        self.captures: list[tuple[str, int]] = []
        # Hooks to stall or observe a call (the concurrency tests).
        self.before_create: Callable[[dict[str, Any]], None] | None = None
        self.before_retrieve: Callable[[str], None] | None = None
        # Errors the next PaymentIntent creations answer with after creating it anyway.
        self.behind_errors: list[Exception] = []
        # Whether Stripe has made a captured payment's balance transaction (its fee) yet.
        self.balance_ready = True
        self.invoices: dict[str, dict[str, Any]] = {}
        # Payments per page of ``InvoicePayment.list`` (Stripe's own limit is 100).
        self.invoice_page_size = 100
        self.PaymentMethod = _PaymentMethodApi(self)
        self.PaymentIntent = _PaymentIntentApi(self)
        self.SetupIntent = _SetupIntentApi(self)
        self.Invoice = _InvoiceApi(self)
        self.InvoicePayment = _InvoicePaymentApi(self)

    @staticmethod
    def fee_for(amount_cents: int) -> int:
        """Stripe's standard US card fee: 2.9% + 30¢."""
        return round(amount_cents * 0.029) + 30

    def balance_transaction(self, intent: dict[str, Any], *, expanded: bool) -> Any:
        """A captured payment's balance transaction: the object when ``expanded``, else
        its id; ``None`` before the money moved, or while ``balance_ready`` is off."""
        received = intent.get("amount_received") or 0
        if intent.get("status") != "succeeded" or not received or not self.balance_ready:
            return None
        transaction_id = f"txn_{intent['id']}"
        if not expanded:
            return transaction_id
        return {
            "id": transaction_id,
            "object": "balance_transaction",
            "amount": received,
            "currency": "usd",
            "fee": self.fee_for(received),
            "net": received - self.fee_for(received),
            "balance_type": "payments",
        }

    def add_invoice(
        self,
        invoice_id: str = "in_order",
        *,
        amount_due: int = 12_000,
        customer: str = STRIPE_CUSTOMER_ID,
        currency: str = "usd",
        status: str = "open",
    ) -> dict[str, Any]:
        """A finalized invoice the project raised for the target (``send_invoice``)."""
        data = {
            "id": invoice_id,
            "object": "invoice",
            "status": status,
            "customer": customer,
            "currency": currency,
            "amount_due": amount_due,
            "amount_paid": 0,
            "amount_remaining": amount_due,
            "collection_method": "send_invoice",
            "attached": [],
        }
        with self.lock:
            self.invoices[invoice_id] = data
        return data

    def add_card(self, pm_id: str = "pm_visa", **fields: Any) -> dict[str, Any]:
        data = payment_method_data(pm_id, **fields)
        self.payment_methods[pm_id] = data
        return data

    def attach(self, setup_intent_id: str) -> None:
        """The SetupIntent succeeded: its card is now attached to its customer."""
        with self.lock:
            data = self.setup_intents[setup_intent_id]
            data["status"] = "succeeded"
            card = self.payment_methods.get(data["payment_method"])
            if card is not None:
                card["customer"] = data["customer"]

    def set_status(self, payment_intent_id: str, status: str) -> None:
        with self.lock:
            self.intents[payment_intent_id]["status"] = status

    def lapse(
        self, payment_intent_id: str, *, canceled: bool = True, reason: str = "expired"
    ) -> None:
        """The authorization expired. Stripe then cancels the PaymentIntent itself
        (``canceled``, ``cancellation_reason="expired"`` from basil on; ``"automatic"``
        before it); before it gets to that, the PaymentIntent still reads
        ``requires_capture`` but a capture is refused with ``charge_expired_for_capture``,
        and a cancel still works."""
        with self.lock:
            data = self.intents[payment_intent_id]
            data["lapsed"] = True
            if canceled:
                data["status"] = "canceled"
                data["cancellation_reason"] = reason

    def fail_behind_next(self, error: Exception | None = None) -> None:
        """The next PaymentIntent creation creates its PaymentIntent but answers with
        ``error`` (a 5xx by default), which Stripe saves for its key like any 5xx."""
        with self.lock:
            self.behind_errors.append(error or api_error())

    def prune_keys(self, *keys: str) -> None:
        """Stripe forgot these idempotency keys (all, without any): pruned after at least
        24 hours, so a repeat runs as a fresh request."""
        with self.lock:
            for key in keys or list(self.replies):
                self.replies.pop(key, None)

    def live_authorizations(self) -> list[str]:
        """PaymentIntents holding money right now (``requires_capture``)."""
        with self.lock:
            return [
                pid for pid, data in self.intents.items() if data["status"] == "requires_capture"
            ]

    def event(self, event_type: str, payment_intent_id: str) -> dict[str, Any]:
        """A Stripe event of ``event_type`` carrying the PaymentIntent as it is now."""
        # A StripeObject's str() is its JSON, nested objects included.
        data = json.loads(str(self.PaymentIntent._construct(payment_intent_id)))
        return {
            "id": f"evt_{next(self.ids)}",
            "object": "event",
            "type": event_type,
            "data": {"object": data},
        }

    def status_of(self, payment_intent_id: str) -> str:
        return self.intents[payment_intent_id]["status"]

    def record(self, _call: str, *args: Any, **kwargs: Any) -> None:
        with self.lock:
            self.calls.append((_call, args, kwargs))

    def fail_next(self, name: str, error: Exception) -> None:
        """Make the next call to ``name`` (e.g. ``"PaymentIntent.cancel"``) raise ``error``."""
        with self.lock:
            self.errors.setdefault(name, []).append(error)

    def raise_queued(self, name: str) -> None:
        with self.lock:
            queued = self.errors.get(name)
            error = queued.pop(0) if queued else None
        if error is not None:
            raise error

    def calls_to(self, name: str) -> list[tuple[tuple, dict]]:
        with self.lock:
            return [(args, kwargs) for called, args, kwargs in self.calls if called == name]


WEBHOOK_SECRET = "whsec_card_holds"


def signed_headers(payload: str, secret: str = WEBHOOK_SECRET) -> dict[str, str]:
    """The ``Stripe-Signature`` header Stripe sends: ``t=<timestamp>,v1=<HMAC-SHA256>``."""
    timestamp = int(time.time())
    signature = hmac.new(
        secret.encode(), f"{timestamp}.{payload}".encode(), hashlib.sha256
    ).hexdigest()
    return {"HTTP_STRIPE_SIGNATURE": f"t={timestamp},v1={signature}"}


def deliver_event(client: Any, event: dict[str, Any], secret: str = WEBHOOK_SECRET) -> Any:
    """POST ``event``, signed, to the webhook endpoint (set ``STRIPE_WEBHOOK_SECRET`` to
    ``secret``), as Stripe delivers it."""
    from django.urls import reverse

    payload = json.dumps(event)
    return client.post(
        reverse("v1:webhooks-stripe-list"),
        data=payload,
        content_type="application/json",
        **signed_headers(payload, secret),
    )
