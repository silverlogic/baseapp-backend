"""One-time purchases (BA-3495): charge products by quantity as one Stripe invoice."""

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import stripe
import swapper
from django.test import RequestFactory
from django.urls import reverse
from rest_framework import status

from baseapp_core.tests.fixtures import Client
from baseapp_core.tests.helpers import responseEquals
from baseapp_payments.models import PurchaseStatus
from baseapp_payments.signals import purchase_failed, purchase_paid
from baseapp_payments.tests.factories import CustomerFactory
from baseapp_payments.tests.helpers import stripe_object
from baseapp_payments.utils import StripeWebhookHandler
from baseapp_profiles.tests.factories import ProfileFactory

pytestmark = pytest.mark.django_db

Purchase = swapper.load_model("baseapp_payments", "Purchase")
PurchaseLine = swapper.load_model("baseapp_payments", "PurchaseLine")

URL = "v1:purchases-list"

PRODUCTS = {
    "prod_a": {"name": "Product A", "price": "price_a", "unit_amount": 1000, "type": "one_time"},
    "prod_b": {"name": "Product B", "price": "price_b", "unit_amount": 450, "type": "one_time"},
    "prod_sub": {"name": "Plan", "price": "price_sub", "unit_amount": 900, "type": "recurring"},
    "prod_eur": {"name": "Euro", "price": "price_eur", "unit_amount": 500, "type": "one_time"},
}


def _product(product_id: str) -> "stripe.StripeObject | None":
    spec = PRODUCTS.get(product_id)
    if spec is None:
        return None
    return stripe_object(
        {
            "id": product_id,
            "name": spec["name"],
            "active": True,
            "default_price": {
                "id": spec["price"],
                "active": True,
                "type": spec["type"],
                "unit_amount": spec["unit_amount"],
                "currency": "eur" if product_id == "prod_eur" else "usd",
            },
        }
    )


def _finalized(invoice_id: str = "in_1", subtotal: int = 3900, tax: int = 0) -> Any:
    return stripe_object(
        {
            "id": invoice_id,
            "status": "open",
            "subtotal": subtotal,
            "total": subtotal + tax,
            "total_excluding_tax": subtotal,
            "confirmation_secret": {"client_secret": "pi_1_secret_x", "type": "payment_intent"},
        }
    )


@pytest.fixture
def stripe_mocks() -> Any:
    with (
        patch("baseapp_payments.purchases.StripeService.retrieve_product") as retrieve_product,
        patch("baseapp_payments.purchases.StripeService.payment_method_belongs_to") as belongs,
        patch("baseapp_payments.purchases.stripe.Invoice.create") as invoice_create,
        patch("baseapp_payments.purchases.stripe.InvoiceItem.create") as item_create,
        patch("baseapp_payments.purchases.stripe.Invoice.finalize_invoice") as finalize,
        patch("baseapp_payments.purchases.stripe.Invoice.void_invoice") as void,
        patch("baseapp_payments.utils.stripe.Subscription.create") as subscription_create,
    ):
        retrieve_product.side_effect = _product
        belongs.return_value = True
        invoice_create.return_value = stripe_object({"id": "in_1"})
        finalize.return_value = _finalized()
        yield MagicMock(
            retrieve_product=retrieve_product,
            belongs=belongs,
            invoice_create=invoice_create,
            item_create=item_create,
            finalize=finalize,
            void=void,
            subscription_create=subscription_create,
        )


def _post(client: Client, customer: Any, items: list, **extra: Any) -> Any:
    return client.post(
        reverse(URL),
        data={"entity_id": str(customer.entity_id), "items": items, **extra},
        content_type="application/json",
    )


class TestCreatePurchase:
    def test_two_products_at_different_quantities(
        self, user_client: Client, stripe_mocks: Any
    ) -> None:
        """Story scenario: 3 × $10.00 + 2 × $4.50 is one payment of $39.00."""
        customer = CustomerFactory(entity=user_client.user.profile, remote_customer_id="cus_1")

        response = _post(
            user_client,
            customer,
            [{"product_id": "prod_a", "quantity": 3}, {"product_id": "prod_b", "quantity": 2}],
            payment_method_id="pm_saved",
        )

        responseEquals(response, status.HTTP_201_CREATED)
        body = response.json()
        assert body["status"] == "pending"
        assert body["subtotal"] == 3900 and body["total"] == 3900 and body["tax"] == 0
        assert body["client_secret"] == "pi_1_secret_x"
        assert [(line["quantity"], line["amount"]) for line in body["lines"]] == [
            (3, 3000),
            (2, 900),
        ]
        purchase = Purchase.objects.get(pk=body["id"])
        assert purchase.remote_invoice_id == "in_1"
        assert purchase.lines.count() == 2
        # One invoice, an item per line priced by Stripe, finalized but not charged.
        invoice_kwargs = stripe_mocks.invoice_create.call_args.kwargs
        assert invoice_kwargs["auto_advance"] is False
        assert invoice_kwargs["pending_invoice_items_behavior"] == "exclude"
        assert invoice_kwargs["default_payment_method"] == "pm_saved"
        assert invoice_kwargs["metadata"] == {"baseapp_purchase_id": str(purchase.pk)}
        assert [
            (c.kwargs["pricing"], c.kwargs["quantity"])
            for c in stripe_mocks.item_create.call_args_list
        ] == [({"price": "price_a"}, 3), ({"price": "price_b"}, 2)]
        # Never the subscription flow.
        stripe_mocks.subscription_create.assert_not_called()

    def test_new_card_needs_no_payment_method(self, user_client: Client, stripe_mocks: Any) -> None:
        customer = CustomerFactory(entity=user_client.user.profile, remote_customer_id="cus_1")
        stripe_mocks.finalize.return_value = _finalized(subtotal=1000)

        response = _post(user_client, customer, [{"product_id": "prod_a", "quantity": 1}])

        responseEquals(response, status.HTTP_201_CREATED)
        assert "default_payment_method" not in stripe_mocks.invoice_create.call_args.kwargs

    @pytest.mark.parametrize("quantity", [0, -1, 1.5, "two"])
    def test_invalid_quantity_is_rejected(
        self, user_client: Client, stripe_mocks: Any, quantity: Any
    ) -> None:
        """Story scenario: a quantity of 0 (or negative) is rejected and nothing is charged."""
        customer = CustomerFactory(entity=user_client.user.profile, remote_customer_id="cus_1")

        response = _post(user_client, customer, [{"product_id": "prod_a", "quantity": quantity}])

        responseEquals(response, status.HTTP_400_BAD_REQUEST)
        stripe_mocks.invoice_create.assert_not_called()
        assert not Purchase.objects.exists()

    def test_modified_price_is_rejected(self, user_client: Client, stripe_mocks: Any) -> None:
        """Story scenario: a price that differs from the product's is rejected."""
        customer = CustomerFactory(entity=user_client.user.profile, remote_customer_id="cus_1")

        response = _post(
            user_client, customer, [{"product_id": "prod_a", "quantity": 1, "unit_amount": 1}]
        )

        responseEquals(response, status.HTTP_400_BAD_REQUEST)
        assert "items" in response.json()
        stripe_mocks.invoice_create.assert_not_called()

    def test_matching_price_is_accepted(self, user_client: Client, stripe_mocks: Any) -> None:
        customer = CustomerFactory(entity=user_client.user.profile, remote_customer_id="cus_1")
        stripe_mocks.finalize.return_value = _finalized(subtotal=1000)

        response = _post(
            user_client, customer, [{"product_id": "prod_a", "quantity": 1, "unit_amount": 1000}]
        )

        responseEquals(response, status.HTTP_201_CREATED)

    @pytest.mark.parametrize(
        "items",
        [
            [{"product_id": "prod_sub", "quantity": 1}],
            [{"product_id": "prod_missing", "quantity": 1}],
            [{"product_id": "prod_a", "quantity": 1}, {"product_id": "prod_eur", "quantity": 1}],
            [{"product_id": "prod_a", "quantity": 1}, {"product_id": "prod_a", "quantity": 2}],
            [],
        ],
        ids=["recurring-price", "unknown-product", "mixed-currency", "duplicate", "empty"],
    )
    def test_items_that_must_not_be_charged(
        self, user_client: Client, stripe_mocks: Any, items: list
    ) -> None:
        customer = CustomerFactory(entity=user_client.user.profile, remote_customer_id="cus_1")

        response = _post(user_client, customer, items)

        responseEquals(response, status.HTTP_400_BAD_REQUEST)
        stripe_mocks.invoice_create.assert_not_called()

    def test_someone_elses_card_is_rejected(self, user_client: Client, stripe_mocks: Any) -> None:
        customer = CustomerFactory(entity=user_client.user.profile, remote_customer_id="cus_1")
        stripe_mocks.belongs.return_value = False

        response = _post(
            user_client,
            customer,
            [{"product_id": "prod_a", "quantity": 1}],
            payment_method_id="pm_other",
        )

        responseEquals(response, status.HTTP_400_BAD_REQUEST)
        assert "payment_method_id" in response.json()
        stripe_mocks.invoice_create.assert_not_called()

    def test_cannot_bill_another_entity(self, user_client: Client, stripe_mocks: Any) -> None:
        other = CustomerFactory(entity=ProfileFactory(), remote_customer_id="cus_other")

        response = _post(user_client, other, [{"product_id": "prod_a", "quantity": 1}])

        responseEquals(response, status.HTTP_403_FORBIDDEN)
        stripe_mocks.invoice_create.assert_not_called()

    def test_anonymous_user_cannot_buy(self, client: Client) -> None:
        response = client.post(reverse(URL), data={}, content_type="application/json")
        responseEquals(response, status.HTTP_401_UNAUTHORIZED)

    def test_stripe_failure_charges_nothing_and_keeps_no_purchase(
        self, user_client: Client, stripe_mocks: Any
    ) -> None:
        customer = CustomerFactory(entity=user_client.user.profile, remote_customer_id="cus_1")
        stripe_mocks.item_create.side_effect = stripe.InvalidRequestError("boom", "price")

        response = _post(user_client, customer, [{"product_id": "prod_a", "quantity": 1}])

        assert response.status_code == 502
        assert "boom" not in response.content.decode()
        stripe_mocks.void.assert_called_once_with("in_1")
        assert not Purchase.objects.exists()

    def test_subtotal_mismatch_voids_the_invoice(
        self, user_client: Client, stripe_mocks: Any
    ) -> None:
        """The price moved between our read and Stripe's: charge nothing unexpected."""
        customer = CustomerFactory(entity=user_client.user.profile, remote_customer_id="cus_1")
        stripe_mocks.finalize.return_value = _finalized(subtotal=9999)

        response = _post(user_client, customer, [{"product_id": "prod_a", "quantity": 1}])

        assert response.status_code == 502
        stripe_mocks.void.assert_called_once_with("in_1")
        assert not Purchase.objects.exists()

    def test_automatic_tax_is_requested_and_stored(
        self, user_client: Client, stripe_mocks: Any, settings: Any
    ) -> None:
        settings.BASEAPP_PAYMENTS_AUTOMATIC_TAX = True
        customer = CustomerFactory(entity=user_client.user.profile, remote_customer_id="cus_1")
        stripe_mocks.finalize.return_value = _finalized(subtotal=1000, tax=80)

        response = _post(user_client, customer, [{"product_id": "prod_a", "quantity": 1}])

        responseEquals(response, status.HTTP_201_CREATED)
        assert stripe_mocks.invoice_create.call_args.kwargs["automatic_tax"] == {"enabled": True}
        assert response.json()["tax"] == 80
        assert response.json()["total"] == 1080


class TestRetrievePurchase:
    def test_owner_reads_the_status(self, user_client: Client) -> None:
        customer = CustomerFactory(entity=user_client.user.profile, remote_customer_id="cus_1")
        purchase = Purchase.objects.create(
            customer=customer, currency="usd", subtotal=1000, total=1000
        )

        response = user_client.get(reverse("v1:purchases-detail", kwargs={"pk": purchase.pk}))

        responseEquals(response, status.HTTP_200_OK)
        assert response.json()["status"] == "pending"

    def test_cannot_read_another_customers_purchase(self, user_client: Client) -> None:
        other = CustomerFactory(entity=ProfileFactory(), remote_customer_id="cus_other")
        purchase = Purchase.objects.create(customer=other, currency="usd", subtotal=1, total=1)

        response = user_client.get(reverse("v1:purchases-detail", kwargs={"pk": purchase.pk}))

        responseEquals(response, status.HTTP_403_FORBIDDEN)


def _event(event_type: str, invoice: dict) -> "stripe.StripeObject":
    return stripe_object({"type": event_type, "data": {"object": invoice}})


def _deliver(event: "stripe.StripeObject") -> Any:
    request = RequestFactory().post(
        "/v1/payments/stripe/webhooks",
        data=b"{}",
        content_type="application/json",
        HTTP_STRIPE_SIGNATURE="sig",
    )
    with patch("baseapp_payments.utils.stripe.Webhook.construct_event", return_value=event):
        return StripeWebhookHandler().webhook_handler(request, "whsec_x")


class TestPurchaseWebhooks:
    @pytest.fixture
    def purchase(self) -> Any:
        customer = CustomerFactory(remote_customer_id="cus_1")
        return Purchase.objects.create(
            customer=customer, currency="usd", subtotal=3900, total=3900, remote_invoice_id="in_1"
        )

    def test_paid_marks_paid_and_fires_once(
        self, purchase: Any, django_capture_on_commit_callbacks: Any
    ) -> None:
        received: list = []
        handler = lambda sender, purchase, **kwargs: received.append(purchase.pk)  # noqa: E731
        purchase_paid.connect(handler)
        try:
            with django_capture_on_commit_callbacks(execute=True):
                assert _deliver(_event("invoice.paid", {"id": "in_1"})).status_code == 200
                # Stripe can deliver an event more than once.
                assert _deliver(_event("invoice.paid", {"id": "in_1"})).status_code == 200
        finally:
            purchase_paid.disconnect(handler)

        purchase.refresh_from_db()
        assert purchase.status == PurchaseStatus.PAID and purchase.paid_at is not None
        assert received == [purchase.pk]

    @patch("baseapp_payments.purchases.stripe.Invoice.void_invoice")
    @patch("baseapp_payments.purchases.stripe.Invoice.retrieve")
    def test_declined_marks_failed_voids_and_fires_once(
        self,
        retrieve: MagicMock,
        void: MagicMock,
        purchase: Any,
        django_capture_on_commit_callbacks: Any,
    ) -> None:
        """Story scenario: a declined card reads "Failed", nothing is charged, event once."""
        retrieve.return_value = stripe_object(
            {
                "id": "in_1",
                "payments": {
                    "data": [{"payment": {"payment_intent": {"status": "requires_payment_method"}}}]
                },
            }
        )
        received: list = []
        handler = lambda sender, purchase, **kwargs: received.append(purchase.pk)  # noqa: E731
        purchase_failed.connect(handler)
        try:
            with django_capture_on_commit_callbacks(execute=True):
                _deliver(_event("invoice.payment_failed", {"id": "in_1"}))
                _deliver(_event("invoice.payment_failed", {"id": "in_1"}))
        finally:
            purchase_failed.disconnect(handler)

        purchase.refresh_from_db()
        assert purchase.status == PurchaseStatus.FAILED
        assert received == [purchase.pk]
        void.assert_called_once_with("in_1")

    @patch("baseapp_payments.purchases.stripe.Invoice.void_invoice")
    @patch("baseapp_payments.purchases.stripe.Invoice.retrieve")
    def test_payment_needing_3ds_is_not_a_failure(
        self, retrieve: MagicMock, void: MagicMock, purchase: Any
    ) -> None:
        retrieve.return_value = stripe_object(
            {
                "id": "in_1",
                "payments": {
                    "data": [{"payment": {"payment_intent": {"status": "requires_action"}}}]
                },
            }
        )

        _deliver(_event("invoice.payment_failed", {"id": "in_1"}))

        purchase.refresh_from_db()
        assert purchase.status == PurchaseStatus.PENDING
        void.assert_not_called()

    def test_subscription_invoices_are_ignored(self, purchase: Any) -> None:
        response = _deliver(_event("invoice.paid", {"id": "in_subscription"}))

        assert response.status_code == 200
        purchase.refresh_from_db()
        assert purchase.status == PurchaseStatus.PENDING
