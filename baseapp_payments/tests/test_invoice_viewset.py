from unittest.mock import MagicMock, patch

import pytest
from django.urls import reverse
from rest_framework import status

from baseapp_core.tests.fixtures import Client
from baseapp_core.tests.helpers import responseEquals
from baseapp_payments.tests.factories import CustomerFactory
from baseapp_payments.tests.helpers import stripe_list
from baseapp_profiles.tests.factories import ProfileFactory

pytestmark = pytest.mark.django_db


class TestInvoiceListView:
    viewname = "v1:customers-invoices"

    def test_anon_user_cannot_get_invoices(self, client: Client) -> None:
        response = client.get(reverse(self.viewname, kwargs={"entity_id": 1}))
        responseEquals(response, status.HTTP_401_UNAUTHORIZED)

    def test_user_cannot_get_invoices_if_customer_not_found(self, user_client: Client) -> None:
        response = user_client.get(reverse(self.viewname, kwargs={"entity_id": 1}))
        responseEquals(response, status.HTTP_404_NOT_FOUND)

    @patch("baseapp_payments.views.StripeService.get_customer_payment_methods")
    def test_user_cannot_list_other_customer_invoices(
        self, mock_get_customer_payment_methods: MagicMock, user_client: Client
    ) -> None:
        mock_get_customer_payment_methods.return_value = []
        customer = CustomerFactory(entity=ProfileFactory(), remote_customer_id="cus_123")
        response = user_client.get(reverse(self.viewname, kwargs={"entity_id": customer.entity_id}))
        responseEquals(response, status.HTTP_403_FORBIDDEN)

    @patch("baseapp_payments.utils.StripeService.list_invoices")
    def test_user_can_get_invoices(
        self, mock_list_invoices: MagicMock, user_client: Client
    ) -> None:
        customer = CustomerFactory(entity=user_client.user.profile, remote_customer_id="cus_123")
        mock_list_invoices.return_value = stripe_list([])
        response = user_client.get(reverse(self.viewname, kwargs={"entity_id": customer.entity_id}))
        responseEquals(response, status.HTTP_200_OK)

        assert mock_list_invoices.call_count == 1


class TestInvoiceClientSecret:
    """`list_invoices` requests no expansion, so `payment_intent` arrives as an id string."""

    def test_unexpanded_payment_intent_serializes_instead_of_raising(
        self, user_client: Client
    ) -> None:
        from baseapp_payments.serializers import StripeInvoiceSerializer

        invoice = {"id": "in_1", "payment_intent": "pi_123", "lines": {"data": []}}

        assert StripeInvoiceSerializer(invoice).data["client_secret"] is None

    def test_expanded_payment_intent_still_yields_the_secret(self, user_client: Client) -> None:
        from baseapp_payments.serializers import StripeInvoiceSerializer

        invoice = {
            "id": "in_1",
            "payment_intent": {"client_secret": "pi_123_secret"},
            "lines": {"data": []},
        }

        assert StripeInvoiceSerializer(invoice).data["client_secret"] == "pi_123_secret"


class TestBasilInvoice:
    """2025-03-31.basil moved the secret to ``confirmation_secret``, a line's ``type`` to
    ``parent.type`` and its ``price`` to ``pricing.price_details.price``."""

    def test_the_confirmation_secret_is_the_client_secret(self) -> None:
        from baseapp_payments.serializers import StripeInvoiceSerializer

        invoice = {
            "id": "in_1",
            "confirmation_secret": {"client_secret": "pi_1_secret", "type": "payment_intent"},
            "lines": {"data": []},
        }

        assert StripeInvoiceSerializer(invoice).data["client_secret"] == "pi_1_secret"

    def test_lines_read_their_type_and_expanded_price_from_basils_places(self) -> None:
        from baseapp_payments.serializers import StripeInvoiceSerializer

        price = {"id": "price_1", "currency": "usd", "unit_amount": 1_000, "recurring": {}}
        invoice = {
            "id": "in_1",
            "lines": {
                "data": [
                    {
                        "id": "il_1",
                        "amount": 1_000,
                        "description": "Plan",
                        "quantity": 1,
                        "parent": {"type": "subscription_item_details"},
                        "pricing": {"type": "price_details", "price_details": {"price": price}},
                    },
                    {
                        "id": "il_2",
                        "amount": 500,
                        "description": "Extra",
                        "quantity": 1,
                        "parent": {"type": "invoice_item_details"},
                        "pricing": {"type": "price_details", "price_details": {"price": "price_2"}},
                    },
                ]
            },
        }

        first, second = StripeInvoiceSerializer(invoice).data["lines"]

        assert first["type"] == "subscription"
        assert first["price"]["id"] == "price_1"
        assert second["type"] == "invoiceitem"
        # Only an id: not enough to fill the nested price, so it is left out.
        assert "price" not in second

    def test_lines_from_before_basil_are_untouched(self) -> None:
        from baseapp_payments.serializers import StripeInvoiceSerializer

        price = {"id": "price_1", "currency": "usd", "unit_amount": 1_000, "recurring": {}}
        line = {
            "id": "il_1",
            "amount": 1,
            "description": "",
            "quantity": 1,
            "type": "subscription",
            "price": price,
        }

        (data,) = StripeInvoiceSerializer({"id": "in_1", "lines": {"data": [line]}}).data["lines"]

        assert data["type"] == "subscription" and data["price"]["id"] == "price_1"
