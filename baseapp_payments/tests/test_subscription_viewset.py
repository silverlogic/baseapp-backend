from unittest.mock import MagicMock, patch

import pytest
import swapper
from django.urls import reverse
from rest_framework import status

from baseapp_core.tests.helpers import responseEquals
from baseapp_payments.tests.factories import CustomerFactory, SubscriptionFactory

pytestmark = pytest.mark.django_db

Subscription = swapper.load_model("baseapp_payments", "Subscription")


class TestSubscriptionCreateView:
    viewname = "v1:subscriptions-list"

    def test_anon_user_cannot_create_subscription(self, client):
        response = client.post(reverse(self.viewname))
        responseEquals(response, status.HTTP_401_UNAUTHORIZED)

    @patch("baseapp_payments.utils.StripeService.create_subscription")
    @patch("baseapp_payments.utils.StripeService.list_subscriptions")
    @patch("baseapp_payments.utils.StripeService.retrieve_price")
    @patch("baseapp_payments.utils.StripeService.retrieve_customer")
    def test_user_can_create_subscription(
        self,
        mock_retrieve_customer,
        mock_retrieve_price,
        mock_list_subscriptions,
        mock_create_subscription,
        user_client,
    ):
        CustomerFactory(entity=user_client.user.profile, remote_customer_id="cus_123")
        mock_retrieve_customer.return_value = {"id": "cus_123"}
        mock_retrieve_price.return_value = {"product": {"id": "prod_123"}}
        mock_list_subscriptions.return_value = []
        mock_create_subscription.return_value = MagicMock(id="sub_123")
        response = user_client.post(
            reverse(self.viewname),
            data={"remote_customer_id": "cus_123", "price_id": "price_123"},
        )
        responseEquals(response, status.HTTP_201_CREATED)
        assert response.json()["remote_subscription_id"] == "sub_123"

    @patch("baseapp_payments.utils.StripeService.retrieve_customer")
    def test_user_cannot_create_subscription_for_other_user_customer(
        self, mock_retrieve_customer, user_client
    ):
        mock_retrieve_customer.return_value = {"id": "cus_123"}
        response = user_client.post(
            reverse(self.viewname),
            data={"remote_customer_id": "cus_other", "price_id": "price_123"},
        )
        responseEquals(response, status.HTTP_400_BAD_REQUEST)

    @patch("baseapp_payments.utils.StripeService.list_subscriptions")
    @patch("baseapp_payments.utils.StripeService.retrieve_price")
    @patch("baseapp_payments.utils.StripeService.retrieve_customer")
    def test_user_cannot_create_duplicate_subscription(
        self,
        mock_retrieve_customer,
        mock_retrieve_price,
        mock_list_subscriptions,
        user_client,
    ):
        CustomerFactory(entity=user_client.user.profile, remote_customer_id="cus_123")
        mock_retrieve_customer.return_value = {"id": "cus_123"}
        mock_retrieve_price.return_value = {"product": {"id": "prod_123"}}
        mock_list_subscriptions.return_value = [
            {
                "status": "active",
                "items": {"data": [{"price": {"id": "price_123", "product": "prod_123"}}]},
            }
        ]
        response = user_client.post(
            reverse(self.viewname),
            data={"remote_customer_id": "cus_123", "price_id": "price_123"},
        )
        responseEquals(response, status.HTTP_400_BAD_REQUEST)


class TestSubscriptionRetrieveView:
    viewname = "v1:subscriptions-detail"

    def test_anon_user_cannot_retrieve_subscription(self, client):
        response = client.get(reverse(self.viewname, kwargs={"remote_subscription_id": "sub_123"}))
        responseEquals(response, status.HTTP_401_UNAUTHORIZED)

    @patch("baseapp_payments.utils.StripeService.retrieve_subscription")
    def test_user_can_retrieve_subscription(self, mock_retrieve_subscription, user_client):
        SubscriptionFactory(remote_subscription_id="sub_123")
        mock_retrieve_subscription.return_value = {"id": "sub_123", "status": "active"}
        response = user_client.get(
            reverse(self.viewname, kwargs={"remote_subscription_id": "sub_123"})
        )
        responseEquals(response, status.HTTP_200_OK)
        assert response.json()["id"] == "sub_123"

    @patch("baseapp_payments.utils.StripeService.retrieve_subscription")
    def test_user_gets_404_for_nonexistent_subscription(
        self, mock_retrieve_subscription, user_client
    ):
        SubscriptionFactory(remote_subscription_id="sub_123")
        mock_retrieve_subscription.return_value = None
        response = user_client.get(
            reverse(self.viewname, kwargs={"remote_subscription_id": "sub_123"})
        )
        responseEquals(response, status.HTTP_404_NOT_FOUND)


class TestSubscriptionPartialUpdateView:
    viewname = "v1:subscriptions-detail"

    def test_anon_user_cannot_update_subscription(self, client):
        response = client.patch(
            reverse(self.viewname, kwargs={"remote_subscription_id": "sub_123"})
        )
        responseEquals(response, status.HTTP_401_UNAUTHORIZED)

    @patch("baseapp_payments.utils.StripeService.update_subscription")
    @patch("baseapp_payments.utils.StripeService.list_payment_methods")
    @patch("baseapp_payments.utils.StripeService.retrieve_customer")
    def test_user_can_update_subscription_payment_method(
        self,
        mock_retrieve_customer,
        mock_list_payment_methods,
        mock_update_subscription,
        user_client,
    ):
        CustomerFactory(entity=user_client.user.profile, remote_customer_id="cus_123")
        SubscriptionFactory(remote_subscription_id="sub_123", remote_customer_id="cus_123")
        mock_retrieve_customer.return_value = {"id": "cus_123"}
        mock_list_payment_methods.return_value = [{"id": "pm_123"}]
        mock_update_subscription.return_value = {}
        response = user_client.patch(
            reverse(self.viewname, kwargs={"remote_subscription_id": "sub_123"}),
            data={"remote_customer_id": "cus_123", "default_payment_method": "pm_123"},
        )
        responseEquals(response, status.HTTP_200_OK)
        assert response.json() == {"status": "success", "message": "Subscription updated in Stripe"}

    @patch("baseapp_payments.utils.StripeService.retrieve_customer")
    def test_user_cannot_update_subscription_with_invalid_customer(
        self, mock_retrieve_customer, user_client
    ):
        SubscriptionFactory(remote_subscription_id="sub_123")
        mock_retrieve_customer.return_value = {"id": "cus_123"}
        response = user_client.patch(
            reverse(self.viewname, kwargs={"remote_subscription_id": "sub_123"}),
            data={"remote_customer_id": "cus_other", "default_payment_method": "pm_123"},
        )
        responseEquals(response, status.HTTP_400_BAD_REQUEST)


class TestSubscriptionDestroyView:
    viewname = "v1:subscriptions-detail"

    def test_anon_user_cannot_delete_subscription(self, client):
        response = client.delete(
            reverse(self.viewname, kwargs={"remote_subscription_id": "sub_123"})
        )
        responseEquals(response, status.HTTP_401_UNAUTHORIZED)

    def test_user_can_delete_subscription(self, user_client):
        SubscriptionFactory(remote_subscription_id="sub_123")
        response = user_client.delete(
            reverse(self.viewname, kwargs={"remote_subscription_id": "sub_123"})
        )
        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert not Subscription.objects.filter(remote_subscription_id="sub_123").exists()

    def test_user_gets_404_deleting_nonexistent_subscription(self, user_client):
        response = user_client.delete(
            reverse(self.viewname, kwargs={"remote_subscription_id": "sub_nonexistent"})
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND
