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

    def test_user_can_get_products(self, user_client):
        response = user_client.get(reverse(self.viewname))
        responseEquals(response, status.HTTP_200_OK)

    @patch("baseapp_payments.views.StripeService.list_products")
    def test_user_can_get_products_with_query_params(self, mock_list_products, user_client):
        mock_list_products.return_value = [{"data": [{"id": "prod_123"}]}]
        response = user_client.get(reverse(self.viewname), {"active": "false"})
        responseEquals(response, status.HTTP_200_OK)
        assert mock_list_products.call_args.kwargs["active"] is False

    @patch("baseapp_payments.views.StripeService.list_products")
    def test_user_can_get_products_filtered_by_category(self, mock_list_products, user_client):
        mock_list_products.return_value = [
            {
                "data": [
                    {"id": "prod_123", "metadata": {"categories": ["test"]}},
                    {"id": "prod_124", "metadata": {"categories": ["test2"]}},
                ]
            }
        ]
        response = user_client.get(reverse(self.viewname), {"category": "test"})
        responseEquals(response, status.HTTP_200_OK)
        assert len(response.data) == 1
        assert response.data[0]["id"] == "prod_123"

    @patch("baseapp_payments.views.StripeService.list_products")
    def test_user_can_get_products_filtered_by_name(self, mock_list_products, user_client):
        mock_list_products.return_value = [
            {
                "data": [
                    {"id": "prod_123", "name": "test"},
                    {"id": "prod_124", "name": "another"},
                    {"id": "prod_125", "description": "test"},
                ]
            }
        ]
        response = user_client.get(reverse(self.viewname), {"name": "test"})
        responseEquals(response, status.HTTP_200_OK)
        assert len(response.data) == 2

    @patch("baseapp_payments.views.StripeService.list_products")
    def test_user_can_get_products_filtered_by_type(self, mock_list_products, user_client):
        mock_list_products.return_value = [
            {
                "data": [
                    {
                        "id": "prod_123",
                        "type": "one_time",
                        "default_price": {"id": "price_123", "recurring": {"interval": "month"}},
                    },
                    {
                        "id": "prod_124",
                        "type": "recurring",
                        "default_price": {"id": "price_124", "recurring": {"interval": "month"}},
                    },
                ]
            }
        ]
        response = user_client.get(reverse(self.viewname), {"type": "one_time"})
        responseEquals(response, status.HTTP_200_OK)
        assert len(response.data) == 1
        assert response.data[0]["id"] == "prod_123"

    @patch("baseapp_payments.views.StripeService.list_products")
    def test_user_can_get_products_filtered_by_price_range(self, mock_list_products, user_client):
        mock_list_products.return_value = [
            {
                "data": [
                    {
                        "id": "prod_123",
                        "default_price": {
                            "id": "price_123",
                            "unit_amount": 1000,
                            "recurring": None,
                        },
                    },
                    {
                        "id": "prod_124",
                        "default_price": {
                            "id": "price_124",
                            "unit_amount": 2000,
                            "recurring": None,
                        },
                    },
                ]
            }
        ]
        response = user_client.get(reverse(self.viewname), {"price_range": [1500, 2000]})
        responseEquals(response, status.HTTP_200_OK)
        assert len(response.data) == 1
        assert response.data[0]["id"] == "prod_123"


class TestProductRetrieveView:
    viewname = "v1:products-detail"

    def test_anon_user_cannot_create_customer(self, client):
        response = client.post(reverse(self.viewname, kwargs={}))
        responseEquals(response, status.HTTP_401_UNAUTHORIZED)

    @patch("baseapp_payments.views.StripeService.retrieve_product")
    def test_user_can_get_product(self, mock_retrieve_product, user_client):
        mock_retrieve_product.return_value = {"id": "prod_123"}
        response = user_client.get(reverse(self.viewname, kwargs={"pk": "prod_123"}))
        responseEquals(response, status.HTTP_200_OK)
