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
