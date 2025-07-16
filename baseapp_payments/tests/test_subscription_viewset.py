from unittest.mock import Mock, patch

import pytest
import swapper
from django.urls import reverse
from rest_framework import status

from baseapp_core.tests.helpers import responseEquals
from baseapp_payments.tests.factories import CustomerFactory, SubscriptionFactory
from baseapp_profiles.tests.factories import ProfileFactory

pytestmark = pytest.mark.django_db


Profile = swapper.load_model("profiles", "Profile")
Customer = swapper.load_model("baseapp_payments", "Customer")
Subscription = swapper.load_model("baseapp_payments", "Subscription")


class TestSubscriptionRetrieveView:
    viewname = "v1:subscriptions-detail"

    def test_anon_user_cannot_get_subscription(self, client):
        response = client.get(reverse(self.viewname, kwargs={"remote_subscription_id": "sub_123"}))
        responseEquals(response, status.HTTP_401_UNAUTHORIZED)

    def test_user_cannot_get_other_customer_subscription(self, user_client):
        customer = CustomerFactory(entity=ProfileFactory(), remote_customer_id="cus_123")
        subscription = SubscriptionFactory(customer=customer)
        response = user_client.get(
            reverse(
                self.viewname,
                kwargs={"remote_subscription_id": subscription.remote_subscription_id},
            )
        )
        responseEquals(response, status.HTTP_403_FORBIDDEN)

    @patch("baseapp_payments.views.StripeService.retrieve_subscription")
    def test_user_can_get_subscription(self, mock_retrieve_subscription, user_client):
        mock_retrieve_subscription.return_value = {
            "id": "sub_123",
            "status": "active",
        }
        customer = CustomerFactory(entity=user_client.user.profile, remote_customer_id="cus_123")
        subscription = SubscriptionFactory(customer=customer)
        response = user_client.get(
            reverse(
                self.viewname,
                kwargs={"remote_subscription_id": subscription.remote_subscription_id},
            )
        )
        responseEquals(response, status.HTTP_200_OK)
        assert response.data["id"] == "sub_123"
        assert response.data["status"] == "active"


class TestSubscriptionListView:
    viewname = "v1:subscriptions-list"

    def test_anon_user_cannot_list_subscriptions(self, client):
        response = client.post(reverse(self.viewname, kwargs={}))
        responseEquals(response, status.HTTP_401_UNAUTHORIZED)

    @patch("baseapp_payments.views.StripeService.list_subscriptions")
    def test_user_can_list_subscriptions(self, mock_list_subscriptions, user_client):
        customer = CustomerFactory(entity=user_client.user.profile, remote_customer_id="cus_123")
        SubscriptionFactory(customer=CustomerFactory())
        subscription = SubscriptionFactory(customer=customer)
        mock_subscriptions = Mock()
        mock_subscriptions.data = [
            {
                "id": subscription.remote_subscription_id,
                "status": "active",
            }
        ]
        mock_list_subscriptions.return_value = mock_subscriptions
        response = user_client.get(
            reverse(self.viewname),
            data={"entity_id": customer.entity_id},
        )
        responseEquals(response, status.HTTP_200_OK)
        assert len(response.data) == 1
        assert response.data[0]["id"] == subscription.remote_subscription_id
        assert response.data[0]["status"] == "active"


class TestSubscriptionCreateView:
    viewname = "v1:subscriptions-list"

    def test_anon_user_cannot_create_subscription(self, client):
        response = client.post(reverse(self.viewname))
        responseEquals(response, status.HTTP_401_UNAUTHORIZED)

    @patch("baseapp_payments.views.StripeService.list_subscriptions")
    @patch("baseapp_payments.views.StripeService.create_subscription")
    @patch("baseapp_payments.views.StripeService.retrieve_price")
    def test_user_can_create_subscription(
        self, mock_retrieve_price, mock_create_subscription, mock_list_subscriptions, user_client
    ):
        mock_retrieve_price = Mock()
        mock_retrieve_price.product = Mock()
        mock_retrieve_price.product.id = "prod_123"
        mock_create_subscription.return_value = {
            "id": "sub_123",
            "status": "active",
        }
        mock_list_subscriptions = Mock()
        mock_list_subscriptions.data = []
        customer = CustomerFactory(entity=user_client.user.profile, remote_customer_id="cus_123")
        response = user_client.post(
            reverse(self.viewname),
            data={"entity_id": customer.entity_id, "price_id": "price_123"},
        )
        responseEquals(response, status.HTTP_201_CREATED)
        assert Subscription.objects.filter(customer=customer).count() == 1
        assert response.data["id"] == "sub_123"
        assert response.data["status"] == "active"

    @patch("baseapp_payments.views.StripeService.list_subscriptions")
    @patch("baseapp_payments.views.StripeService.create_incomplete_subscription")
    @patch("baseapp_payments.views.StripeService.retrieve_price")
    def test_user_can_create_incomplete_subscription(
        self,
        mock_retrieve_price,
        mock_create_incomplete_subscription,
        mock_list_subscriptions,
        user_client,
    ):
        mock_retrieve_price = Mock()
        mock_retrieve_price.product = Mock()
        mock_retrieve_price.product.id = "prod_123"
        mock_subscription = Mock()
        mock_subscription.get = Mock(
            side_effect=lambda key, default=None: {"id": "sub_123", "status": "incomplete"}.get(
                key, default
            )
        )
        mock_subscription.id = "sub_123"
        mock_subscription.status = "incomplete"
        mock_subscription.get_client_secret = Mock(return_value="client_secret_123")
        mock_latest_invoice = Mock()
        mock_latest_invoice.items = Mock(
            return_value=[("payment_intent", {"client_secret": "client_secret_123"})]
        )
        mock_subscription.latest_invoice = mock_latest_invoice
        mock_create_incomplete_subscription.return_value = mock_subscription
        mock_list_subscriptions = Mock()
        mock_list_subscriptions.data = []
        customer = CustomerFactory(entity=user_client.user.profile, remote_customer_id="cus_123")
        response = user_client.post(
            reverse(self.viewname),
            data={
                "entity_id": customer.entity_id,
                "price_id": "price_123",
                "allow_incomplete": True,
            },
        )
        responseEquals(response, status.HTTP_201_CREATED)
        assert Subscription.objects.filter(customer=customer).count() == 1
        assert response.data["id"] == "sub_123"
        assert response.data["status"] == "incomplete"
        assert response.data["client_secret"] is not None


class TestSubscriptionUpdateView:
    viewname = "v1:subscriptions-detail"

    def test_anon_user_cannot_update_subscription(self, client):
        response = client.patch(
            reverse(self.viewname, kwargs={"remote_subscription_id": "sub_123"})
        )
        responseEquals(response, status.HTTP_401_UNAUTHORIZED)

    def test_user_cannot_update_other_customer_subscription(self, user_client):
        customer = CustomerFactory(entity=ProfileFactory(), remote_customer_id="cus_123")
        subscription = SubscriptionFactory(customer=customer)
        response = user_client.patch(
            reverse(
                self.viewname,
                kwargs={"remote_subscription_id": subscription.remote_subscription_id},
            ),
            data={"payment_method_id": "pm_123"},
        )
        responseEquals(response, status.HTTP_403_FORBIDDEN)

    @patch("baseapp_payments.views.StripeService.update_subscription")
    @patch("baseapp_payments.views.StripeService.list_payment_methods")
    def test_user_can_update_subscription_payment_method(
        self, mock_list_payment_methods, mock_update_subscription, user_client
    ):
        mock_list_payment_methods.return_value = [
            {
                "id": "pm_123",
                "type": "card",
            }
        ]
        mock_update_subscription.return_value = {
            "id": "sub_123",
            "status": "active",
        }
        customer = CustomerFactory(entity=user_client.user.profile, remote_customer_id="cus_123")
        subscription = SubscriptionFactory(customer=customer)
        response = user_client.patch(
            reverse(
                self.viewname,
                kwargs={"remote_subscription_id": subscription.remote_subscription_id},
            ),
            data={"payment_method_id": "pm_123"},
        )
        responseEquals(response, status.HTTP_200_OK)
        assert mock_update_subscription.call_count == 1


class TestSubscriptionDeleteView:
    viewname = "v1:subscriptions-detail"

    def test_anon_user_cannot_delete_subscription(self, client):
        response = client.delete(
            reverse(self.viewname, kwargs={"remote_subscription_id": "sub_123"})
        )
        responseEquals(response, status.HTTP_401_UNAUTHORIZED)

    def test_user_cannot_delete_other_customer_subscription(self, user_client):
        customer = CustomerFactory(entity=ProfileFactory(), remote_customer_id="cus_124")
        subscription = SubscriptionFactory(customer=customer)
        response = user_client.delete(
            reverse(
                self.viewname,
                kwargs={"remote_subscription_id": subscription.remote_subscription_id},
            ),
        )
        responseEquals(response, status.HTTP_403_FORBIDDEN)

    @patch("baseapp_payments.views.StripeService.delete_subscription")
    def test_user_can_delete_subscription(self, mock_delete_subscription, user_client):
        mock_delete_subscription.return_value = None
        customer = CustomerFactory(entity=user_client.user.profile, remote_customer_id="cus_123")
        subscription = SubscriptionFactory(customer=customer)
        response = user_client.delete(
            reverse(
                self.viewname,
                kwargs={"remote_subscription_id": subscription.remote_subscription_id},
            ),
        )
        responseEquals(response, status.HTTP_204_NO_CONTENT)
        assert not Subscription.objects.filter(id=subscription.id).exists()
        assert mock_delete_subscription.call_count == 1
