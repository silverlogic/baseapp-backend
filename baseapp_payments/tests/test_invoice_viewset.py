from unittest.mock import patch

import pytest
from django.urls import reverse
from rest_framework import status

from baseapp_core.tests.helpers import responseEquals
from baseapp_payments.tests.factories import CustomerFactory

pytestmark = pytest.mark.django_db


class TestInvoiceListView:
    viewname = "v1:invoices-list"

    def test_anon_user_cannot_get_invoices(self, client):
        response = client.get(reverse(self.viewname))
        responseEquals(response, status.HTTP_401_UNAUTHORIZED)

    def test_user_cannot_get_invoices_if_customer_not_found(self, user_client):
        response = user_client.get(reverse(self.viewname))
        responseEquals(response, status.HTTP_404_NOT_FOUND)

    @patch("baseapp_payments.utils.StripeService.get_user_invoices")
    def test_user_can_get_invoices(self, mock_get_user_invoices, user_client):
        CustomerFactory(entity=user_client.user.profile, remote_customer_id="cus_123")
        mock_get_user_invoices.return_value = []
        response = user_client.get(reverse(self.viewname))
        responseEquals(response, status.HTTP_200_OK)

        assert mock_get_user_invoices.call_count == 1
