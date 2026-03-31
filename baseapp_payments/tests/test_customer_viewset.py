from unittest.mock import patch

import pytest
import swapper
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from rest_framework import status

from baseapp_core.tests.helpers import responseEquals
from baseapp_payments.tests.factories import CustomerFactory

pytestmark = pytest.mark.django_db


Profile = swapper.load_model("profiles", "Profile")
Customer = swapper.load_model("baseapp_payments", "Customer")


class TestCustomerRetrieveView:
    viewname = "v1:customers-detail"

    def test_anon_user_cannot_get_customer(self, client):
        response = client.get(reverse(self.viewname, kwargs={"pk": "me"}))
        responseEquals(response, status.HTTP_401_UNAUTHORIZED)

    def test_user_can_get_self_customer_with_existing_db_entry(self, user_client):
        CustomerFactory(entity=user_client.user.profile, remote_customer_id="cus_123")
        response = user_client.get(reverse(self.viewname, kwargs={"pk": "me"}))
        responseEquals(response, status.HTTP_200_OK)

    @patch("baseapp_payments.views.StripeService.retrieve_customer")
    def test_user_can_get_self_customer_with_existing_stripe_entry(
        self, mock_retrieve_customer, user_client
    ):
        mock_retrieve_customer.return_value = {"id": "cus_123"}
        response = user_client.get(reverse(self.viewname, kwargs={"pk": "me"}))
        responseEquals(response, status.HTTP_200_OK)
        assert Customer.objects.filter(
            entity_id=user_client.user.profile.id,
            entity_type=ContentType.objects.get_for_model(Profile),
            remote_customer_id="cus_123",
        ).exists()


class TestCustomerCreateView:
    viewname = "v1:customers-list"

    def test_anon_user_cannot_create_customer(self, client):
        response = client.post(reverse(self.viewname, kwargs={}))
        responseEquals(response, status.HTTP_401_UNAUTHORIZED)

    @patch("baseapp_payments.views.StripeService.create_customer")
    def test_user_can_create_customer(self, mock_create_customer, user_client):
        mock_create_customer.return_value = {"id": "cus_123"}
        response = user_client.post(reverse(self.viewname))
        responseEquals(response, status.HTTP_201_CREATED)
        assert Customer.objects.all().count() == 1
        assert Customer.objects.filter(
            entity_id=user_client.user.profile.id,
            entity_type=ContentType.objects.get_for_model(Profile),
        ).exists()
