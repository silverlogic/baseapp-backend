from unittest.mock import patch

import pytest
from django.urls import reverse
from rest_framework import status

from baseapp_core.tests.helpers import responseEquals
from baseapp_payments.tests.factories import CustomerFactory

pytestmark = pytest.mark.django_db


class TestPaymentMethodListView:
    viewname = "v1:payment-methods-list"

    def test_anon_user_cannot_list_payment_methods(self, client):
        response = client.get(reverse(self.viewname))
        responseEquals(response, status.HTTP_401_UNAUTHORIZED)

    def test_user_cannot_list_self_payment_methods_without_customer_id(self, user_client):
        response = user_client.get(reverse(self.viewname))
        responseEquals(response, status.HTTP_400_BAD_REQUEST)
        assert response.json() == {"error": "Missing customer_id"}

    @patch("baseapp_payments.views.StripeService.retrieve_customer")
    @patch("baseapp_payments.views.StripeService.get_customer_payment_methods")
    def test_user_can_list_self_payment_methods(
        self, mock_get_customer_payment_methods, mock_retrieve_customer, user_client
    ):
        CustomerFactory(entity=user_client.user.profile, remote_customer_id="cus_123")
        mock_retrieve_customer.return_value = {"id": "cus_123"}
        mock_get_customer_payment_methods.return_value = [{"id": "pm_123"}]
        response = user_client.get(reverse(self.viewname), data={"customer_id": "cus_123"})
        responseEquals(response, status.HTTP_200_OK)
        assert response.json() == [{"id": "pm_123", "is_default": False}]


class TestPaymentMethodUpdateView:
    viewname = "v1:payment-methods-detail"

    def test_anon_user_cannot_create_payment_method(self, client):
        response = client.put(reverse(self.viewname, kwargs={"pk": "pm_123"}))
        responseEquals(response, status.HTTP_401_UNAUTHORIZED)

    @patch("baseapp_payments.views.StripeService.update_customer")
    @patch("baseapp_payments.views.StripeService.retrieve_customer")
    def test_user_can_update_payment_method(
        self, mock_retrieve_customer, mock_update_customer, user_client
    ):
        mock_retrieve_customer.return_value = {"id": "cus_123"}
        mock_update_customer.return_value = {"id": "pm_123"}
        CustomerFactory(entity=user_client.user.profile, remote_customer_id="cus_123")
        response = user_client.put(
            reverse(self.viewname, kwargs={"pk": "pm_123"}),
            data={
                "customer_id": "cus_123",
                "default_payment_method_id": "pm_456",
            },
        )
        responseEquals(response, status.HTTP_200_OK)


class TestPaymentMethodDeleteView:
    viewname = "v1:payment-methods-detail"

    def test_anon_user_cannot_delete_payment_method(self, client):
        response = client.delete(reverse(self.viewname, kwargs={"pk": "pm_123"}))
        responseEquals(response, status.HTTP_401_UNAUTHORIZED)

    def test_user_cannot_delete_payment_method_without_customer_id(self, user_client):
        response = user_client.delete(reverse(self.viewname, kwargs={"pk": "pm_123"}))
        responseEquals(response, status.HTTP_400_BAD_REQUEST)
        assert response.json() == {"error": "Missing customer_id"}

    @patch("baseapp_payments.views.StripeService.retrieve_customer")
    def test_user_cannot_delete_other_user_payment_method(
        self, mock_retrieve_customer, user_client
    ):
        mock_retrieve_customer.return_value = {"id": "cus_123"}
        CustomerFactory(entity=user_client.user.profile, remote_customer_id="cus_123")
        response = user_client.delete(
            reverse(self.viewname, kwargs={"pk": "pm_123"}) + "?customer_id=cus_432",
        )
        responseEquals(response, status.HTTP_401_UNAUTHORIZED)
        assert response.json() == {
            "error": "The provided customer_id does not belong to the authenticated user."
        }

    @patch("baseapp_payments.views.StripeService.retrieve_customer")
    @patch("baseapp_payments.views.StripeService.delete_payment_method")
    def test_user_can_delete_payment_method(
        self, mock_delete_payment_method, mock_retrieve_customer, user_client
    ):
        mock_retrieve_customer.return_value = {"id": "cus_123"}
        mock_delete_payment_method.return_value = {}
        CustomerFactory(entity=user_client.user.profile, remote_customer_id="cus_123")
        response = user_client.delete(
            reverse(self.viewname, kwargs={"pk": "pm_123"}) + "?customer_id=cus_123",
        )
        responseEquals(response, status.HTTP_204_NO_CONTENT)
