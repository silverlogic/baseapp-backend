from unittest.mock import patch

import pytest
from django.urls import reverse
from rest_framework import status

from baseapp_core.tests.helpers import responseEquals

pytestmark = pytest.mark.django_db


class TestProductListView:
    viewname = "v1:products-list"

    def test_anon_user_cannot_list_products(self, client):
        response = client.get(reverse(self.viewname))
        responseEquals(response, status.HTTP_401_UNAUTHORIZED)

    @patch("baseapp_payments.utils.StripeService.list_products")
    def test_user_can_list_products(self, mock_list_products, user_client):
        mock_list_products.return_value = [
            {
                "id": "prod_123",
                "name": "Pro Plan",
                "description": "Professional plan",
                "active": True,
                "default_price": {
                    "id": "price_123",
                    "currency": "usd",
                    "unit_amount": 2000,
                    "recurring": {"interval": "month"},
                },
            }
        ]
        response = user_client.get(reverse(self.viewname))
        responseEquals(response, status.HTTP_200_OK)


class TestProductRetrieveView:
    viewname = "v1:products-detail"

    def test_anon_user_cannot_retrieve_product(self, client):
        response = client.get(reverse(self.viewname, kwargs={"remote_product_id": "prod_123"}))
        responseEquals(response, status.HTTP_401_UNAUTHORIZED)

    @patch("baseapp_payments.utils.StripeService.retrieve_product")
    def test_user_can_retrieve_product(self, mock_retrieve_product, user_client):
        mock_retrieve_product.return_value = {
            "id": "prod_123",
            "name": "Pro Plan",
            "description": "Professional plan",
            "active": True,
            "default_price": {
                "id": "price_123",
                "currency": "usd",
                "unit_amount": 2000,
                "recurring": {"interval": "month"},
            },
        }
        response = user_client.get(reverse(self.viewname, kwargs={"remote_product_id": "prod_123"}))
        responseEquals(response, status.HTTP_200_OK)
        assert response.json()["id"] == "prod_123"
        assert response.json()["name"] == "Pro Plan"

    @patch("baseapp_payments.utils.StripeService.retrieve_product")
    def test_user_gets_404_for_nonexistent_product(self, mock_retrieve_product, user_client):
        mock_retrieve_product.return_value = None
        response = user_client.get(
            reverse(self.viewname, kwargs={"remote_product_id": "prod_nonexistent"})
        )
        responseEquals(response, status.HTTP_404_NOT_FOUND)
