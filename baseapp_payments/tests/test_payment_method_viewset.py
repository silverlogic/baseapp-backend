from unittest.mock import patch

import pytest
import stripe
from django.urls import reverse
from rest_framework import status

from baseapp_core.tests.helpers import responseEquals
from baseapp_payments.tests.factories import CustomerFactory
from baseapp_payments.tests.helpers import stripe_list
from baseapp_profiles.tests.factories import ProfileFactory

pytestmark = pytest.mark.django_db


class TestPaymentMethodListView:
    viewname = "v1:customers-payment-methods"

    def test_anon_user_cannot_list_payment_methods(self, client) -> None:
        response = client.get(reverse(self.viewname, kwargs={"entity_id": 1}))
        responseEquals(response, status.HTTP_401_UNAUTHORIZED)

    @patch("baseapp_payments.views.StripeService.get_customer_payment_methods")
    def test_user_cannot_list_other_customer_payment_methods(
        self, mock_get_customer_payment_methods, user_client
    ) -> None:
        mock_get_customer_payment_methods.return_value = []
        customer = CustomerFactory(entity=ProfileFactory(), remote_customer_id="cus_123")
        response = user_client.get(reverse(self.viewname, kwargs={"entity_id": customer.entity_id}))
        responseEquals(response, status.HTTP_403_FORBIDDEN)

    @patch("baseapp_payments.views.StripeService.retrieve_customer")
    @patch("baseapp_payments.views.StripeService.get_customer_payment_methods")
    def test_user_can_list_self_payment_methods(
        self, mock_get_customer_payment_methods, mock_retrieve_customer, user_client
    ) -> None:
        customer = CustomerFactory(entity=user_client.user.profile, remote_customer_id="cus_123")
        mock_retrieve_customer.return_value = {"id": "cus_123"}
        mock_get_customer_payment_methods.return_value = [{"id": "pm_123"}]
        response = user_client.get(
            reverse(self.viewname, kwargs={"entity_id": customer.entity_id}),
            data={"customer_id": "cus_123"},
        )
        responseEquals(response, status.HTTP_200_OK)
        assert response.json() == [{"id": "pm_123", "is_default": False}]


class TestPaymentMethodUpdateView:
    viewname = "v1:customers-payment-methods"

    def test_anon_user_cannot_create_payment_method(self, client) -> None:
        response = client.put(
            reverse(self.viewname, kwargs={"entity_id": 1, "payment_method_id": "pm_123"})
        )
        responseEquals(response, status.HTTP_401_UNAUTHORIZED)

    @patch("baseapp_payments.views.StripeService.get_customer_payment_methods")
    def test_user_cannot_update_other_customer_payment_method(
        self, mock_get_customer_payment_methods, user_client
    ) -> None:
        mock_get_customer_payment_methods.return_value = []
        customer = CustomerFactory(entity=ProfileFactory(), remote_customer_id="cus_123")
        response = user_client.put(
            reverse(
                self.viewname,
                kwargs={"entity_id": customer.entity_id, "payment_method_id": "pm_123"},
            )
        )
        responseEquals(response, status.HTTP_403_FORBIDDEN)

    @patch("baseapp_payments.views.StripeService.list_payment_methods")
    @patch("baseapp_payments.views.StripeService.update_customer")
    def test_user_can_update_payment_method(
        self, mock_update_customer, mock_list_payment_methods, user_client
    ) -> None:
        mock_update_customer.return_value = {"id": "pm_123"}
        mock_list_payment_methods.return_value = stripe_list([{"id": "pm_123"}])
        customer = CustomerFactory(entity=user_client.user.profile, remote_customer_id="cus_123")
        response = user_client.put(
            reverse(
                self.viewname,
                kwargs={"entity_id": customer.entity_id, "payment_method_id": "pm_123"},
            ),
            data={
                "customer_id": "cus_123",
                "default_payment_method_id": "pm_456",
            },
        )
        responseEquals(response, status.HTTP_200_OK)


class TestPaymentMethodDeleteView:
    viewname = "v1:customers-payment-methods"

    def test_anon_user_cannot_delete_payment_method(self, client) -> None:
        response = client.delete(
            reverse(self.viewname, kwargs={"entity_id": 1, "payment_method_id": "pm_123"})
        )
        responseEquals(response, status.HTTP_401_UNAUTHORIZED)

    @patch("baseapp_payments.views.StripeService.delete_payment_method")
    def test_user_cannot_delete_other_user_payment_method(
        self, mock_delete_payment_method, user_client
    ) -> None:
        mock_delete_payment_method.return_value = {}
        customer = CustomerFactory(entity=ProfileFactory(), remote_customer_id="cus_123")
        response = user_client.delete(
            reverse(
                self.viewname,
                kwargs={"entity_id": customer.entity_id, "payment_method_id": "pm_123"},
            )
            + "?customer_id=cus_432",
        )
        responseEquals(response, status.HTTP_403_FORBIDDEN)

    @patch("baseapp_payments.views.StripeService.list_payment_methods")
    @patch("baseapp_payments.views.StripeService.retrieve_customer")
    @patch("baseapp_payments.views.StripeService.delete_payment_method")
    def test_user_can_delete_payment_method(
        self,
        mock_delete_payment_method,
        mock_retrieve_customer,
        mock_list_payment_methods,
        user_client,
    ) -> None:
        mock_retrieve_customer.return_value = {"id": "cus_123"}
        mock_delete_payment_method.return_value = {}
        mock_list_payment_methods.return_value = stripe_list([{"id": "pm_123"}])
        customer = CustomerFactory(entity=user_client.user.profile, remote_customer_id="cus_123")
        response = user_client.delete(
            reverse(
                self.viewname,
                kwargs={"entity_id": customer.entity_id, "payment_method_id": "pm_123"},
            )
            + "?customer_id=cus_123",
        )
        responseEquals(response, status.HTTP_204_NO_CONTENT)


class TestPaymentMethodFailures:
    viewname = "v1:customers-payment-methods"

    @patch("baseapp_payments.views.StripeService.get_customer_payment_methods")
    def test_listing_failure_does_not_leak_details(
        self, mock_get_customer_payment_methods, user_client
    ):
        mock_get_customer_payment_methods.side_effect = Exception("stripe down: sk_test_secret")
        customer = CustomerFactory(entity=user_client.user.profile, remote_customer_id="cus_123")
        response = user_client.get(reverse(self.viewname, kwargs={"entity_id": customer.entity_id}))
        responseEquals(response, status.HTTP_500_INTERNAL_SERVER_ERROR)
        assert response.data == {"error": "An internal error has occurred"}

    @patch("baseapp_payments.views.StripeService.create_setup_intent")
    def test_creating_a_setup_intent(self, mock_create_setup_intent, user_client):
        mock_create_setup_intent.return_value = {"id": "seti_1", "client_secret": "cs_1"}
        customer = CustomerFactory(entity=user_client.user.profile, remote_customer_id="cus_123")
        response = user_client.post(
            reverse(self.viewname, kwargs={"entity_id": customer.entity_id})
        )
        responseEquals(response, status.HTTP_201_CREATED)
        assert response.data["client_secret"] == "cs_1"

    @patch("baseapp_payments.views.StripeService.create_setup_intent")
    def test_setup_intent_failure_does_not_leak_details(
        self, mock_create_setup_intent, user_client
    ):
        mock_create_setup_intent.side_effect = Exception("stripe down: sk_test_secret")
        customer = CustomerFactory(entity=user_client.user.profile, remote_customer_id="cus_123")
        response = user_client.post(
            reverse(self.viewname, kwargs={"entity_id": customer.entity_id})
        )
        assert response.status_code in (400, 500)
        assert "sk_test_secret" not in str(response.data)


class TestPaymentMethodOutageIsNotAMissingCard:
    """A Stripe failure during the ownership check must not read as a deleted card."""

    viewname = "v1:customers-payment-methods"

    @patch("baseapp_payments.views.StripeService.payment_method_belongs_to")
    def test_update_answers_503_when_stripe_is_unreachable(self, mock_belongs_to, user_client):
        mock_belongs_to.side_effect = stripe.APIConnectionError("stripe unreachable")
        customer = CustomerFactory(entity=user_client.user.profile, remote_customer_id="cus_123")
        response = user_client.patch(
            reverse(
                self.viewname,
                kwargs={"entity_id": customer.entity_id, "payment_method_id": "pm_123"},
            ),
            data={"billing_details": {"name": "New Name"}},
        )
        responseEquals(response, status.HTTP_503_SERVICE_UNAVAILABLE)

    @patch("baseapp_payments.views.StripeService.payment_method_belongs_to")
    def test_delete_answers_503_when_stripe_is_unreachable(self, mock_belongs_to, user_client):
        mock_belongs_to.side_effect = stripe.APIConnectionError("stripe unreachable")
        customer = CustomerFactory(entity=user_client.user.profile, remote_customer_id="cus_123")
        response = user_client.delete(
            reverse(
                self.viewname,
                kwargs={"entity_id": customer.entity_id, "payment_method_id": "pm_123"},
            )
            + "?customer_id=cus_123",
        )
        responseEquals(response, status.HTTP_503_SERVICE_UNAVAILABLE)
