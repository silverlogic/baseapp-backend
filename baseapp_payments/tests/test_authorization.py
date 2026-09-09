"""Authorization regression tests addressed by relay id.

The existing 403 tests all address entities by raw integer pk. That is the one
lookup shape `StripeCustomerViewset.get_object()` used to hand to DRF, so it was
also the only shape whose object permissions ran - a relay id, which is what the
client actually sends, returned the object unchecked. These mirror those tests
with relay ids so the branch real traffic takes is the one under test.
"""

from unittest.mock import patch

import pytest
from django.urls import reverse
from rest_framework import status

from baseapp_core.tests.helpers import responseEquals
from baseapp_payments.tests.factories import CustomerFactory
from baseapp_payments.tests.helpers import stripe_list
from baseapp_profiles.tests.factories import ProfileFactory

pytestmark = pytest.mark.django_db


def other_customer():
    return CustomerFactory(entity=ProfileFactory(), remote_customer_id="cus_victim")


class TestCustomerRoutesRejectRelayIdsOfOtherEntities:
    @patch("baseapp_payments.views.StripeService.retrieve_customer")
    @patch("baseapp_payments.views.StripeService.get_customer_payment_methods")
    def test_cannot_list_other_entity_payment_methods_by_relay_id(
        self, mock_get_pms, mock_retrieve, user_client
    ):
        mock_retrieve.return_value = {"id": "cus_victim"}
        mock_get_pms.return_value = [{"id": "pm_victim_card"}]
        victim = other_customer()
        response = user_client.get(
            reverse(
                "v1:customers-payment-methods",
                kwargs={"entity_id": victim.entity.relay_id},
            )
        )
        responseEquals(response, status.HTTP_403_FORBIDDEN)

    @patch("baseapp_payments.views.StripeService.delete_payment_method")
    def test_cannot_delete_other_entity_payment_method_by_relay_id(self, mock_delete, user_client):
        mock_delete.return_value = {}
        victim = other_customer()
        response = user_client.delete(
            reverse(
                "v1:customers-payment-methods",
                kwargs={"entity_id": victim.entity.relay_id, "payment_method_id": "pm_123"},
            )
        )
        responseEquals(response, status.HTTP_403_FORBIDDEN)
        assert not mock_delete.called

    @patch("baseapp_payments.utils.StripeService.list_invoices")
    def test_cannot_list_other_entity_invoices_by_relay_id(self, mock_list_invoices, user_client):
        mock_list_invoices.return_value = stripe_list([{"id": "in_victim"}])
        victim = other_customer()
        response = user_client.get(
            reverse("v1:customers-invoices", kwargs={"entity_id": victim.entity.relay_id})
        )
        responseEquals(response, status.HTTP_403_FORBIDDEN)

    def test_can_still_reach_own_customer_by_relay_id(self, user_client):
        own = CustomerFactory(entity=user_client.user.profile, remote_customer_id="cus_mine")
        with patch("baseapp_payments.utils.StripeService.list_invoices") as mock_list_invoices:
            mock_list_invoices.return_value = stripe_list([])
            response = user_client.get(
                reverse("v1:customers-invoices", kwargs={"entity_id": own.entity.relay_id})
            )
        responseEquals(response, status.HTTP_200_OK)


class TestSubscriptionCreateAuthorization:
    viewname = "v1:subscriptions-list"

    @patch("baseapp_payments.views.StripeService.create_subscription")
    @patch("baseapp_payments.views.StripeService.list_subscriptions")
    @patch("baseapp_payments.views.StripeService.retrieve_price")
    def test_cannot_create_subscription_on_another_entity(
        self, mock_price, mock_list_subs, mock_create, user_client
    ):
        mock_price.return_value = {"id": "price_1", "product": {"id": "prod_1"}}
        mock_list_subs.return_value = stripe_list([])
        mock_create.return_value = {"id": "sub_new", "status": "active"}
        victim = other_customer()
        response = user_client.post(
            reverse(self.viewname),
            data={"entity_id": victim.entity.relay_id, "price_id": "price_1"},
        )
        responseEquals(response, status.HTTP_403_FORBIDDEN)
        # The billing call is the thing that must not happen, not just the 403.
        assert not mock_create.called

    def test_create_without_entity_id_is_rejected(self, user_client):
        response = user_client.post(reverse(self.viewname), data={"price_id": "price_1"})
        responseEquals(response, status.HTTP_400_BAD_REQUEST)

    def test_create_with_unknown_entity_id_is_not_found(self, user_client):
        response = user_client.post(
            reverse(self.viewname),
            data={"entity_id": "not-a-relay-id", "price_id": "price_1"},
        )
        responseEquals(response, status.HTTP_404_NOT_FOUND)


class TestSubscriptionListAuthorization:
    viewname = "v1:subscriptions-list"

    @patch("baseapp_payments.views.StripeService.list_subscriptions")
    def test_cannot_list_other_entity_subscriptions(self, mock_list_subs, user_client):
        mock_list_subs.return_value = stripe_list([{"id": "sub_victim", "status": "active"}])
        victim = other_customer()
        response = user_client.get(
            reverse(self.viewname), data={"entity_id": victim.entity.relay_id}
        )
        responseEquals(response, status.HTTP_403_FORBIDDEN)

    def test_list_with_raw_integer_entity_id_is_not_found(self, user_client):
        # A non-relay id resolves to "", which used to reach the pk field and 500.
        response = user_client.get(reverse(self.viewname), data={"entity_id": "7"})
        responseEquals(response, status.HTTP_404_NOT_FOUND)
