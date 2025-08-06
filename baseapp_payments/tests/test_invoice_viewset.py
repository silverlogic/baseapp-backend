from unittest.mock import Mock, patch

import pytest
from django.urls import reverse
from rest_framework import status

from baseapp_core.tests.helpers import responseEquals
from baseapp_payments.tests.factories import CustomerFactory
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

    @patch("baseapp_payments.utils.StripeService.get_customer_invoices")
    def test_user_can_get_invoices(self, mock_get_customer_invoices, user_client):
        customer = CustomerFactory(entity=user_client.user.profile, remote_customer_id="cus_123")
        mock_invoices = []
        mock_get_customer_invoices.return_value = mock_invoices
        response = user_client.get(reverse(self.viewname, kwargs={"entity_id": customer.entity_id}))
        responseEquals(response, status.HTTP_200_OK)

        assert mock_get_customer_invoices.call_count == 1
