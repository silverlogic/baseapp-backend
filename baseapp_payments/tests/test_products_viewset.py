from unittest.mock import patch

import pytest
from django.urls import reverse
from rest_framework import status

from baseapp_core.tests.helpers import responseEquals

pytestmark = pytest.mark.django_db


class TestProductListView:
    viewname = "v1:products-list"

    def test_anon_user_cannot_get_products(self, client):
        response = client.get(reverse(self.viewname))
        responseEquals(response, status.HTTP_401_UNAUTHORIZED)

    @patch("baseapp_payments.views.StripeService.list_products")
    def test_user_can_get_products(self, mock_list_products, user_client):
        mock_list_products.return_value = [
            {
                "id": "prod_123",
                "name": "Product 1",
                "default_price": {
                    "id": "price_123",
                    "unit_amount": 1000,
                    "currency": "USD",
                    "recurring": {"interval": "month", "interval_count": 1},
                },
                "active": True,
                "marketing_features": [],
            }
        ]
        response = user_client.get(reverse(self.viewname))
        responseEquals(response, status.HTTP_200_OK)


class TestProductRetrieveView:
    viewname = "v1:products-detail"

    def test_anon_user_cannot_create_customer(self, client):
        response = client.post(reverse(self.viewname, kwargs={"pk": "prod_123"}))
        responseEquals(response, status.HTTP_401_UNAUTHORIZED)

    @patch("baseapp_payments.views.StripeService.retrieve_product")
    def test_user_can_get_product(self, mock_retrieve_product, user_client):
        mock_retrieve_product.return_value = {
            "id": "prod_123",
            "name": "Product 1",
            "default_price": {
                "id": "price_123",
                "unit_amount": 1000,
                "currency": "USD",
                "recurring": {"interval": "month", "interval_count": 1},
            },
            "active": True,
            "marketing_features": [],
        }
        response = user_client.get(reverse(self.viewname, kwargs={"pk": "prod_123"}))
        responseEquals(response, status.HTTP_200_OK)

    @patch("baseapp_payments.views.StripeService.retrieve_product")
    def test_unknown_product_is_a_404(self, mock_retrieve_product, user_client):
        mock_retrieve_product.return_value = None
        response = user_client.get(reverse(self.viewname, kwargs={"pk": "prod_nope"}))
        responseEquals(response, status.HTTP_404_NOT_FOUND)

    @patch("baseapp_payments.views.StripeService.retrieve_product")
    def test_stripe_failure_does_not_leak_details(self, mock_retrieve_product, user_client):
        mock_retrieve_product.side_effect = Exception("stripe down: sk_test_secret")
        response = user_client.get(reverse(self.viewname, kwargs={"pk": "prod_123"}))
        responseEquals(response, status.HTTP_500_INTERNAL_SERVER_ERROR)
        assert response.data == {"error": "An internal error has occurred"}


class TestProductListFailures:
    viewname = "v1:products-list"

    @patch("baseapp_payments.views.StripeService.list_products")
    def test_stripe_failure_does_not_leak_details(self, mock_list_products, user_client):
        mock_list_products.side_effect = Exception("stripe down: sk_test_secret")
        response = user_client.get(reverse(self.viewname))
        responseEquals(response, status.HTTP_500_INTERNAL_SERVER_ERROR)
        assert response.data == {"error": "An internal error has occurred"}
