import json
from unittest.mock import patch

import pytest
import swapper
from django.test import RequestFactory
from django.urls import reverse
from rest_framework import status

from baseapp_payments.tests.factories import (
    CustomerFactory,
    SubscriptionFactory,
    UserFactory,
)
from baseapp_payments.utils import StripeWebhookHandler

pytestmark = pytest.mark.django_db

Customer = swapper.load_model("baseapp_payments", "Customer")
Subscription = swapper.load_model("baseapp_payments", "Subscription")


def _event(event_type, obj):
    return {"type": event_type, "data": {"object": obj}}


def _post(body=b"{}", **headers):
    return RequestFactory().post(
        "/v1/payments/stripe/webhooks", data=body, content_type="application/json", **headers
    )


class TestWebhookSignature:
    def test_missing_signature_header_is_a_bad_request_not_a_crash(self):
        """The webhook route is unauthenticated, so an unsigned POST must not raise."""
        response = StripeWebhookHandler().webhook_handler(_post(), "whsec_123")
        assert response.status_code == 400

    def test_missing_signature_header_over_http(self, client):
        response = client.post(
            reverse("v1:webhooks-stripe-list"),
            data="{}",
            content_type="application/json",
        )
        # The view returns a plain JsonResponse, so assert on the status directly.
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    @patch("baseapp_payments.utils.stripe.Webhook.construct_event")
    def test_unknown_event_type_is_acknowledged(self, mock_construct):
        # Stripe retries anything that is not a 2xx, so unhandled types must still 200.
        mock_construct.return_value = _event("invoice.paid", {})
        response = StripeWebhookHandler().webhook_handler(
            _post(**{"HTTP_STRIPE_SIGNATURE": "sig"}), "whsec_123"
        )
        assert response.status_code == 200


class TestCustomerEvents:
    @patch("baseapp_payments.utils.stripe.Webhook.construct_event")
    def test_customer_created_links_the_stripe_customer_to_the_profile(self, mock_construct):
        user = UserFactory()
        mock_construct.return_value = _event(
            "customer.created",
            {"id": "cus_new", "metadata": {"entity_id": str(user.profile.id)}},
        )
        response = StripeWebhookHandler().webhook_handler(
            _post(**{"HTTP_STRIPE_SIGNATURE": "sig"}), "whsec_123"
        )
        assert response.status_code == 200
        customer = Customer.objects.get(remote_customer_id="cus_new")
        assert customer.entity == user.profile

    @patch("baseapp_payments.utils.stripe.Webhook.construct_event")
    def test_customer_created_is_idempotent(self, mock_construct):
        """Stripe redelivers events, so a repeat must not create a second row."""
        customer = CustomerFactory(remote_customer_id="cus_dupe")
        mock_construct.return_value = _event(
            "customer.created", {"id": "cus_dupe", "metadata": {"entity_id": "1"}}
        )
        response = StripeWebhookHandler().webhook_handler(
            _post(**{"HTTP_STRIPE_SIGNATURE": "sig"}), "whsec_123"
        )
        assert response.status_code == 200
        assert Customer.objects.filter(remote_customer_id="cus_dupe").count() == 1
        assert Customer.objects.get(remote_customer_id="cus_dupe").pk == customer.pk

    @patch("baseapp_payments.utils.stripe.Webhook.construct_event")
    def test_customer_created_for_an_unknown_email_does_not_500(self, mock_construct):
        mock_construct.return_value = _event(
            "customer.created", {"id": "cus_x", "metadata": {"entity_id": "999999"}}
        )
        response = StripeWebhookHandler().webhook_handler(
            _post(**{"HTTP_STRIPE_SIGNATURE": "sig"}), "whsec_123"
        )
        assert response.status_code == 500
        assert json.loads(response.content) == {"error": "Error"}
        assert not Customer.objects.filter(remote_customer_id="cus_x").exists()

    @patch("baseapp_payments.utils.stripe.Webhook.construct_event")
    def test_customer_deleted_removes_only_that_customer(self, mock_construct):
        CustomerFactory(remote_customer_id="cus_gone")
        survivor = CustomerFactory(remote_customer_id="cus_stays")
        mock_construct.return_value = _event("customer.deleted", {"id": "cus_gone"})
        response = StripeWebhookHandler().webhook_handler(
            _post(**{"HTTP_STRIPE_SIGNATURE": "sig"}), "whsec_123"
        )
        assert response.status_code == 200
        assert not Customer.objects.filter(remote_customer_id="cus_gone").exists()
        assert Customer.objects.filter(pk=survivor.pk).exists()


class TestSubscriptionEvents:
    @patch("baseapp_payments.utils.stripe.Webhook.construct_event")
    def test_subscription_created_records_the_stripe_customer_id(self, mock_construct):
        CustomerFactory(remote_customer_id="cus_123")
        mock_construct.return_value = _event(
            "customer.subscription.created", {"id": "sub_new", "customer": "cus_123"}
        )
        response = StripeWebhookHandler().webhook_handler(
            _post(**{"HTTP_STRIPE_SIGNATURE": "sig"}), "whsec_123"
        )
        assert response.status_code == 200
        subscription = Subscription.objects.get(remote_subscription_id="sub_new")
        assert subscription.customer.remote_customer_id == "cus_123"

    @patch("baseapp_payments.utils.stripe.Webhook.construct_event")
    def test_subscription_created_is_idempotent(self, mock_construct):
        SubscriptionFactory(
            customer=CustomerFactory(remote_customer_id="cus_123"),
            remote_subscription_id="sub_dupe",
        )
        mock_construct.return_value = _event(
            "customer.subscription.created", {"id": "sub_dupe", "customer": "cus_123"}
        )
        response = StripeWebhookHandler().webhook_handler(
            _post(**{"HTTP_STRIPE_SIGNATURE": "sig"}), "whsec_123"
        )
        assert response.status_code == 200
        assert Subscription.objects.filter(remote_subscription_id="sub_dupe").count() == 1

    @patch("baseapp_payments.utils.stripe.Webhook.construct_event")
    def test_subscription_deleted_removes_the_row(self, mock_construct):
        SubscriptionFactory(remote_subscription_id="sub_bye")
        mock_construct.return_value = _event("customer.subscription.deleted", {"id": "sub_bye"})
        response = StripeWebhookHandler().webhook_handler(
            _post(**{"HTTP_STRIPE_SIGNATURE": "sig"}), "whsec_123"
        )
        assert response.status_code == 200
        assert not Subscription.objects.filter(remote_subscription_id="sub_bye").exists()
