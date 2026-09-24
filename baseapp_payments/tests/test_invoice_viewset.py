from unittest.mock import patch

import pytest
from django.urls import reverse
from rest_framework import status

from baseapp_core.tests.helpers import responseEquals
from baseapp_payments.tests.factories import CustomerFactory
from baseapp_payments.tests.helpers import stripe_list
from baseapp_profiles.tests.factories import ProfileFactory

pytestmark = pytest.mark.django_db


class TestInvoiceListView:
    viewname = "v1:customers-invoices"

    def test_anon_user_cannot_get_invoices(self, client):
        response = client.get(reverse(self.viewname, kwargs={"entity_id": 1}))
        responseEquals(response, status.HTTP_401_UNAUTHORIZED)

    def test_user_cannot_get_invoices_if_customer_not_found(self, user_client):
        response = user_client.get(reverse(self.viewname, kwargs={"entity_id": 1}))
        responseEquals(response, status.HTTP_404_NOT_FOUND)

    @patch("baseapp_payments.views.StripeService.get_customer_payment_methods")
    def test_user_cannot_list_other_customer_invoices(
        self, mock_get_customer_payment_methods, user_client
    ):
        mock_get_customer_payment_methods.return_value = []
        customer = CustomerFactory(entity=ProfileFactory(), remote_customer_id="cus_123")
        response = user_client.get(reverse(self.viewname, kwargs={"entity_id": customer.entity_id}))
        responseEquals(response, status.HTTP_403_FORBIDDEN)

    @patch("baseapp_payments.utils.StripeService.list_invoices")
    def test_user_can_get_invoices(self, mock_list_invoices, user_client):
        customer = CustomerFactory(entity=user_client.user.profile, remote_customer_id="cus_123")
        mock_list_invoices.return_value = stripe_list([])
        response = user_client.get(reverse(self.viewname, kwargs={"entity_id": customer.entity_id}))
        responseEquals(response, status.HTTP_200_OK)

        assert mock_list_invoices.call_count == 1


class TestInvoiceClientSecret:
    """`list_invoices` requests no expansion, so `payment_intent` arrives as an id string."""

    def test_unexpanded_payment_intent_serializes_instead_of_raising(self, user_client):
        from baseapp_payments.serializers import StripeInvoiceSerializer

        invoice = {"id": "in_1", "payment_intent": "pi_123", "lines": {"data": []}}

        assert StripeInvoiceSerializer(invoice).data["client_secret"] is None

    def test_expanded_payment_intent_still_yields_the_secret(self, user_client):
        from baseapp_payments.serializers import StripeInvoiceSerializer

        invoice = {
            "id": "in_1",
            "payment_intent": {"client_secret": "pi_123_secret"},
            "lines": {"data": []},
        }

        assert StripeInvoiceSerializer(invoice).data["client_secret"] == "pi_123_secret"
