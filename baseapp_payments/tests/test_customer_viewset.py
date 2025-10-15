from unittest.mock import patch

import pytest
import swapper
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from rest_framework import status

from baseapp_core.graphql.utils import get_obj_relay_id
from baseapp_core.tests.helpers import responseEquals
from baseapp_payments.tests.factories import CustomerFactory

pytestmark = pytest.mark.django_db


Profile = swapper.load_model("profiles", "Profile")
Customer = swapper.load_model("baseapp_payments", "Customer")


class TestCustomerRetrieveView:
    viewname = "v1:customers-detail"

    def test_anon_user_cannot_get_customer(self, client):
        response = client.get(reverse(self.viewname, kwargs={"entity_id": 1}))
        responseEquals(response, status.HTTP_401_UNAUTHORIZED)

    @patch("baseapp_payments.views.StripeService.list_subscriptions")
    def test_user_can_get_customer(self, mock_list_subscriptions, user_client):
        mock_list_subscriptions.return_value.data = []
        customer = CustomerFactory(entity=user_client.user.profile, remote_customer_id="cus_123")
        response = user_client.get(reverse(self.viewname, kwargs={"entity_id": customer.entity_id}))
        responseEquals(response, status.HTTP_200_OK)

    @patch("baseapp_payments.views.StripeService.list_subscriptions")
    def test_user_can_get_customer_me(self, mock_list_subscriptions, user_client):
        mock_list_subscriptions.return_value.data = []
        customer = CustomerFactory(entity=user_client.user.profile, remote_customer_id="cus_123")
        response = user_client.get(reverse(self.viewname, kwargs={"entity_id": "me"}))
        responseEquals(response, status.HTTP_200_OK)
        assert response.data["remote_customer_id"] == customer.remote_customer_id


class TestCustomerCreateView:
    viewname = "v1:customers-list"

    def test_anon_user_cannot_create_customer(self, client):
        response = client.post(reverse(self.viewname, kwargs={}))
        responseEquals(response, status.HTTP_401_UNAUTHORIZED)

    @patch("baseapp_payments.views.StripeService.list_subscriptions")
    @patch("baseapp_payments.views.StripeService.create_customer")
    def test_user_can_create_customer(self, mock_create_customer, mock_list_subscriptions, user_client):
        mock_list_subscriptions.return_value.data = []
        mock_create_customer.return_value = {"id": "cus_123"}
        relay_id = get_obj_relay_id(user_client.user.profile)
        response = user_client.post(
            reverse(self.viewname),
            data={"entity_id": relay_id},
        )
        responseEquals(response, status.HTTP_201_CREATED)
        assert Customer.objects.all().count() == 1
        assert Customer.objects.filter(
            entity_id=user_client.user.profile.id,
            entity_type=ContentType.objects.get_for_model(Profile),
        ).exists()
