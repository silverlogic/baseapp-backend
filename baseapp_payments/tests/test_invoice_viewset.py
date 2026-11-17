from unittest.mock import MagicMock, patch

import pytest
from django.urls import reverse
from rest_framework import status

from baseapp_core.tests.fixtures import Client
from baseapp_core.tests.helpers import responseEquals
from baseapp_payments.tests.factories import CustomerFactory
from baseapp_payments.tests.helpers import stripe_list, stripe_object
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
    """The secret lives on `confirmation_secret`, which `list_invoices` does not expand."""

    def test_unexpanded_confirmation_secret_serializes_as_none(self, user_client: Client) -> None:
        from baseapp_payments.serializers import StripeInvoiceSerializer

        invoice = stripe_object({"id": "in_1", "lines": {"data": []}})

        assert StripeInvoiceSerializer(invoice).data["client_secret"] is None

    def test_expanded_confirmation_secret_yields_the_secret(self, user_client: Client) -> None:
        from baseapp_payments.serializers import StripeInvoiceSerializer

        invoice = stripe_object(
            {
                "id": "in_1",
                "confirmation_secret": {"client_secret": "pi_123_secret", "type": "payment_intent"},
                "lines": {
                    "data": [
                        {
                            "id": "il_1",
                            "amount": 500,
                            "description": "Pro",
                            "quantity": 1,
                            "currency": "usd",
                            # Endive shape: `type` and `price` moved under parent/pricing.
                            "parent": {"type": "subscription_item_details"},
                            "pricing": {
                                "type": "price_details",
                                "price_details": {"price": "price_1", "product": "prod_1"},
                                "unit_amount_decimal": "500",
                            },
                        }
                    ]
                },
                "metadata": {"order": "42"},
            }
        )

        data = StripeInvoiceSerializer(invoice).data
        assert data["client_secret"] == "pi_123_secret"
        line = data["lines"][0]
        assert line["id"] == "il_1"
        assert line["type"] == "subscription"
        assert line["price"]["id"] == "price_1"
        assert line["price"]["currency"] == "usd"
        assert line["price"]["unit_amount"] == 500
        assert data["metadata"] == {"order": "42"}

    def test_sub_cent_unit_amount_is_none_not_truncated(self, user_client: Client) -> None:
        """unit_amount is an integer field; "12.5" has no integer form."""
        from baseapp_payments.utils import invoice_line_legacy_fields

        line = {
            "currency": "usd",
            "pricing": {"price_details": {"price": "price_1"}, "unit_amount_decimal": "12.5"},
        }
        assert invoice_line_legacy_fields(line)["price"]["unit_amount"] is None
        line["pricing"]["unit_amount_decimal"] = "1200.000000000"
        assert invoice_line_legacy_fields(line)["price"]["unit_amount"] == 1200

    def test_legacy_line_shape_is_kept(self, user_client: Client) -> None:
        """A line that still carries top-level type and price serializes as before."""
        from baseapp_payments.serializers import StripeInvoiceLineSerializer

        line = {
            "id": "il_1",
            "amount": 500,
            "description": "Pro",
            "quantity": 1,
            "type": "invoiceitem",
            "price": {"id": "price_1", "currency": "usd", "unit_amount": 500, "recurring": None},
        }

        data = StripeInvoiceLineSerializer(line).data
        assert data["type"] == "invoiceitem"
        assert data["price"]["id"] == "price_1"
