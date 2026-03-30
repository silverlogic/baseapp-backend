from unittest.mock import patch

import pytest
import swapper

from baseapp_payments.tests.factories import CustomerFactory, SubscriptionFactory
from baseapp_payments.utils import StripeWebhookHandler

pytestmark = pytest.mark.django_db

Customer = swapper.load_model("baseapp_payments", "Customer")
Subscription = swapper.load_model("baseapp_payments", "Subscription")


class TestCustomerCreatedHandler:
    @patch("baseapp_payments.utils.config")
    def test_creates_customer_for_existing_user(self, mock_config, user_client):
        mock_config.STRIPE_CUSTOMER_ENTITY_MODEL = "profiles.Profile"
        event = {
            "data": {
                "object": {
                    "id": "cus_new",
                    "email": user_client.user.email,
                }
            }
        }
        response = StripeWebhookHandler.customer_created(event)
        assert response.status_code == 200
        assert Customer.objects.filter(remote_customer_id="cus_new").exists()

    @patch("baseapp_payments.utils.config")
    def test_skips_existing_customer(self, mock_config, user_client):
        mock_config.STRIPE_CUSTOMER_ENTITY_MODEL = "profiles.Profile"
        CustomerFactory(entity=user_client.user.profile, remote_customer_id="cus_existing")
        event = {
            "data": {
                "object": {
                    "id": "cus_existing",
                    "email": user_client.user.email,
                }
            }
        }
        response = StripeWebhookHandler.customer_created(event)
        assert response.status_code == 200
        assert Customer.objects.filter(remote_customer_id="cus_existing").count() == 1

    def test_returns_500_for_unknown_user_email(self):
        event = {
            "data": {
                "object": {
                    "id": "cus_orphan",
                    "email": "unknown@example.com",
                }
            }
        }
        response = StripeWebhookHandler.customer_created(event)
        assert response.status_code == 500


class TestCustomerDeletedHandler:
    def test_deletes_existing_customer(self, user_client):
        CustomerFactory(entity=user_client.user.profile, remote_customer_id="cus_to_delete")
        event = {"data": {"object": {"id": "cus_to_delete"}}}
        response = StripeWebhookHandler.customer_deleted(event)
        assert response.status_code == 200
        assert not Customer.objects.filter(remote_customer_id="cus_to_delete").exists()

    def test_returns_200_for_nonexistent_customer(self):
        event = {"data": {"object": {"id": "cus_nonexistent"}}}
        response = StripeWebhookHandler.customer_deleted(event)
        assert response.status_code == 200


class TestSubscriptionCreatedHandler:
    def test_creates_subscription(self):
        event = {
            "data": {
                "object": {
                    "id": "sub_new",
                    "customer": "cus_123",
                }
            }
        }
        response = StripeWebhookHandler.subscription_created(event)
        assert response.status_code == 200
        assert Subscription.objects.filter(remote_subscription_id="sub_new").exists()
        sub = Subscription.objects.get(remote_subscription_id="sub_new")
        assert sub.remote_customer_id == "cus_123"

    def test_skips_existing_subscription(self):
        SubscriptionFactory(remote_subscription_id="sub_existing", remote_customer_id="cus_123")
        event = {
            "data": {
                "object": {
                    "id": "sub_existing",
                    "customer": "cus_123",
                }
            }
        }
        response = StripeWebhookHandler.subscription_created(event)
        assert response.status_code == 200
        assert Subscription.objects.filter(remote_subscription_id="sub_existing").count() == 1


class TestSubscriptionDeletedHandler:
    def test_deletes_existing_subscription(self):
        SubscriptionFactory(remote_subscription_id="sub_to_delete", remote_customer_id="cus_123")
        event = {"data": {"object": {"id": "sub_to_delete"}}}
        response = StripeWebhookHandler.subscription_deleted(event)
        assert response.status_code == 200
        assert not Subscription.objects.filter(remote_subscription_id="sub_to_delete").exists()

    def test_returns_200_for_nonexistent_subscription(self):
        event = {"data": {"object": {"id": "sub_nonexistent"}}}
        response = StripeWebhookHandler.subscription_deleted(event)
        assert response.status_code == 200
