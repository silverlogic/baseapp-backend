from unittest.mock import patch

import pytest
import swapper
from django.urls import reverse
from rest_framework import status

from baseapp_core.tests.helpers import responseEquals
from baseapp_payments.tests.factories import CustomerFactory, SubscriptionFactory
from baseapp_payments.tests.helpers import stripe_list
from baseapp_profiles.tests.factories import ProfileFactory

pytestmark = pytest.mark.django_db


class _AttrSubscription(dict):
    """Stripe objects expose keys as attributes; the code reads both forms."""

    __getattr__ = dict.__getitem__


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
        mock_list_subscriptions.return_value = stripe_list(
            [{"id": subscription.remote_subscription_id, "status": "active"}]
        )
        response = user_client.get(
            reverse(self.viewname),
            data={"entity_id": customer.entity.relay_id},
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
        mock_retrieve_price.return_value = {"id": "price_123", "product": {"id": "prod_123"}}
        mock_list_subscriptions.return_value = stripe_list([])
        mock_create_subscription.return_value = {
            "id": "sub_123",
            "status": "active",
        }
        customer = CustomerFactory(entity=user_client.user.profile, remote_customer_id="cus_123")
        response = user_client.post(
            reverse(self.viewname),
            data={"entity_id": customer.entity.relay_id, "price_id": "price_123"},
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
        mock_retrieve_price.return_value = {"id": "price_123", "product": {"id": "prod_123"}}
        mock_list_subscriptions.return_value = stripe_list([])
        mock_create_incomplete_subscription.return_value = {
            "id": "sub_123",
            "status": "incomplete",
            "latest_invoice": {"payment_intent": {"client_secret": "client_secret_123"}},
        }
        customer = CustomerFactory(entity=user_client.user.profile, remote_customer_id="cus_123")
        response = user_client.post(
            reverse(self.viewname),
            data={
                "entity_id": customer.entity.relay_id,
                "price_id": "price_123",
                "allow_incomplete": True,
            },
        )
        responseEquals(response, status.HTTP_201_CREATED)
        assert Subscription.objects.filter(customer=customer).count() == 1
        assert response.data["id"] == "sub_123"
        assert response.data["status"] == "incomplete"
        assert response.data["client_secret"] == "client_secret_123"


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
    @patch("baseapp_payments.views.StripeService.retrieve_subscription")
    def test_user_can_update_subscription_payment_method(
        self,
        mock_retrieve_subscription,
        mock_list_payment_methods,
        mock_update_subscription,
        user_client,
    ):
        mock_list_payment_methods.return_value = stripe_list([{"id": "pm_123", "type": "card"}])
        mock_update_subscription.return_value = {
            "id": "sub_123",
            "status": "active",
        }
        mock_retrieve_subscription.return_value = {
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
            data={"default_payment_method": "pm_123"},
        )
        responseEquals(response, status.HTTP_200_OK)
        assert mock_update_subscription.call_count == 1


class TestSubscriptionChangePlanView:
    viewname = "v1:subscriptions-detail"

    @patch("baseapp_payments.views.StripeService.update_subscription")
    @patch("baseapp_payments.views.StripeService.retrieve_subscription")
    @patch("baseapp_payments.views.StripeService.list_payment_methods")
    def test_changing_plan_swaps_the_subscription_item(
        self,
        mock_list_payment_methods,
        mock_retrieve_subscription,
        mock_update_subscription,
        user_client,
    ):
        mock_list_payment_methods.return_value = stripe_list([{"id": "pm_123"}])
        mock_retrieve_subscription.return_value = _AttrSubscription(
            id="sub_123",
            items={"data": [{"id": "si_old"}]},
            default_payment_method="pm_other",
        )
        mock_update_subscription.return_value = {"id": "sub_123", "status": "active"}
        customer = CustomerFactory(entity=user_client.user.profile, remote_customer_id="cus_123")
        subscription = SubscriptionFactory(customer=customer)
        response = user_client.patch(
            reverse(
                self.viewname,
                kwargs={"remote_subscription_id": subscription.remote_subscription_id},
            ),
            data={"price_id": "price_new", "payment_method_id": "pm_123"},
        )
        responseEquals(response, status.HTTP_200_OK)
        fields = mock_update_subscription.call_args.kwargs
        # The old item is removed and the new price added in the same call, so the
        # customer is never briefly subscribed to both or to neither.
        assert fields["items"] == [
            {"id": "si_old", "deleted": True},
            {"price": "price_new"},
        ]
        assert fields["default_payment_method"] == "pm_123"

    @patch("baseapp_payments.views.StripeService.update_payment_method")
    @patch("baseapp_payments.views.StripeService.update_subscription")
    @patch("baseapp_payments.views.StripeService.retrieve_subscription")
    @patch("baseapp_payments.views.StripeService.list_payment_methods")
    def test_a_billing_only_change_succeeds_instead_of_reporting_nothing_to_update(
        self,
        mock_list_payment_methods,
        mock_retrieve_subscription,
        mock_update_subscription,
        mock_update_payment_method,
        user_client,
    ):
        """Stripe has already taken the billing change by this point.

        The card is already the subscription default and no price is sent, so nothing
        about the subscription itself changes. Answering "Nothing to update." here
        reported a failure for work that had landed.
        """
        mock_list_payment_methods.return_value = stripe_list([{"id": "pm_123"}])
        mock_retrieve_subscription.return_value = _AttrSubscription(
            id="sub_123",
            items={"data": [{"id": "si_1"}]},
            default_payment_method="pm_123",
        )
        customer = CustomerFactory(entity=user_client.user.profile, remote_customer_id="cus_123")
        subscription = SubscriptionFactory(customer=customer)
        response = user_client.patch(
            reverse(
                self.viewname,
                kwargs={"remote_subscription_id": subscription.remote_subscription_id},
            ),
            data={"payment_method_id": "pm_123", "billing_details": {"name": "New Name"}},
        )
        responseEquals(response, status.HTTP_200_OK)
        assert mock_update_payment_method.call_count == 1
        mock_update_subscription.assert_not_called()

    @patch("baseapp_payments.views.StripeService.update_payment_method")
    @patch("baseapp_payments.views.StripeService.update_subscription")
    @patch("baseapp_payments.views.StripeService.retrieve_subscription")
    @patch("baseapp_payments.views.StripeService.list_payment_methods")
    def test_a_failed_billing_update_is_not_reported_as_success(
        self,
        mock_list_payment_methods,
        mock_retrieve_subscription,
        mock_update_subscription,
        mock_update_payment_method,
        user_client,
    ):
        mock_list_payment_methods.return_value = stripe_list([{"id": "pm_123"}])
        mock_retrieve_subscription.return_value = _AttrSubscription(
            id="sub_123",
            items={"data": [{"id": "si_old"}]},
            default_payment_method="pm_other",
        )
        mock_update_payment_method.side_effect = Exception("billing rejected")
        customer = CustomerFactory(entity=user_client.user.profile, remote_customer_id="cus_123")
        subscription = SubscriptionFactory(customer=customer)
        response = user_client.patch(
            reverse(
                self.viewname,
                kwargs={"remote_subscription_id": subscription.remote_subscription_id},
            ),
            data={
                "price_id": "price_new",
                "payment_method_id": "pm_123",
                "billing_details": {"name": "New Name"},
            },
        )
        assert response.status_code != status.HTTP_200_OK
        mock_update_subscription.assert_not_called()

    @patch("baseapp_payments.views.StripeService.retrieve_subscription")
    @patch("baseapp_payments.views.StripeService.list_payment_methods")
    def test_a_card_that_is_not_the_customers_is_rejected(
        self, mock_list_payment_methods, mock_retrieve_subscription, user_client
    ):
        mock_list_payment_methods.return_value = stripe_list([{"id": "pm_mine"}])
        customer = CustomerFactory(entity=user_client.user.profile, remote_customer_id="cus_123")
        subscription = SubscriptionFactory(customer=customer)
        response = user_client.patch(
            reverse(
                self.viewname,
                kwargs={"remote_subscription_id": subscription.remote_subscription_id},
            ),
            data={"price_id": "price_new", "payment_method_id": "pm_theirs"},
        )
        responseEquals(response, status.HTTP_400_BAD_REQUEST)
        mock_retrieve_subscription.assert_not_called()

    @patch("baseapp_payments.views.StripeService.update_subscription")
    @patch("baseapp_payments.views.StripeService.retrieve_subscription")
    @patch("baseapp_payments.views.StripeService.list_payment_methods")
    def test_both_payment_method_fields_can_be_sent_together(
        self,
        mock_list_payment_methods,
        mock_retrieve_subscription,
        mock_update_subscription,
        user_client,
    ):
        """Both fields are validated against the same list. Iterating a generator
        twice would exhaust it and reject the second one every time."""
        mock_list_payment_methods.return_value = stripe_list([{"id": "pm_a"}, {"id": "pm_b"}])
        mock_retrieve_subscription.return_value = _AttrSubscription(
            id="sub_123", items={"data": [{"id": "si_old"}]}, default_payment_method="pm_a"
        )
        mock_update_subscription.return_value = {"id": "sub_123", "status": "active"}
        customer = CustomerFactory(entity=user_client.user.profile, remote_customer_id="cus_123")
        subscription = SubscriptionFactory(customer=customer)
        response = user_client.patch(
            reverse(
                self.viewname,
                kwargs={"remote_subscription_id": subscription.remote_subscription_id},
            ),
            data={"default_payment_method": "pm_a", "payment_method_id": "pm_b"},
        )
        responseEquals(response, status.HTTP_200_OK)


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


class TestSubscriptionListStatusFilter:
    viewname = "v1:subscriptions-list"

    @patch("baseapp_payments.views.StripeService.list_subscriptions")
    def test_status_all_is_forwarded_to_stripe(self, mock_list_subscriptions, user_client):
        """Dropping it fell back to Stripe's default, which excludes canceled ones."""
        mock_list_subscriptions.return_value = stripe_list([])
        customer = CustomerFactory(entity=user_client.user.profile, remote_customer_id="cus_123")
        response = user_client.get(
            reverse(self.viewname),
            data={"entity_id": customer.entity.relay_id, "status": "all"},
        )

        responseEquals(response, status.HTTP_200_OK)
        assert mock_list_subscriptions.call_args.kwargs["status"] == "all"

    @patch("baseapp_payments.views.StripeService.list_subscriptions")
    def test_an_unknown_status_is_a_client_error_not_a_500(
        self, mock_list_subscriptions, user_client
    ):
        customer = CustomerFactory(entity=user_client.user.profile, remote_customer_id="cus_123")
        response = user_client.get(
            reverse(self.viewname),
            data={"entity_id": customer.entity.relay_id, "status": "bogus"},
        )

        responseEquals(response, status.HTTP_400_BAD_REQUEST)
        mock_list_subscriptions.assert_not_called()


class TestChangePlanWithUnexpandedStripeShapes:
    """Changing plan is a create for a customer who already has a subscription.

    Every other create test mocks `product` expanded and an empty subscription list,
    so the combination a real plan change hits - an existing subscription, and Stripe
    answering with bare ids - went unexercised.
    """

    viewname = "v1:subscriptions-list"

    @patch("baseapp_payments.views.StripeService.list_subscriptions")
    @patch("baseapp_payments.views.StripeService.create_incomplete_subscription")
    @patch("baseapp_payments.views.StripeService.retrieve_price")
    def test_plan_change_survives_unexpanded_products(
        self,
        mock_retrieve_price,
        mock_create_incomplete_subscription,
        mock_list_subscriptions,
        user_client,
    ):
        mock_retrieve_price.return_value = {"id": "price_new", "product": "prod_new"}
        mock_list_subscriptions.return_value = stripe_list(
            [
                {
                    "id": "sub_existing",
                    "status": "active",
                    "items": {"data": [{"price": {"id": "price_old", "product": "prod_old"}}]},
                }
            ]
        )
        mock_create_incomplete_subscription.return_value = {
            "id": "sub_new",
            "status": "incomplete",
            "latest_invoice": "in_1",
        }
        customer = CustomerFactory(entity=user_client.user.profile, remote_customer_id="cus_123")
        response = user_client.post(
            reverse(self.viewname),
            data={
                "entity_id": customer.entity.relay_id,
                "price_id": "price_new",
                "allow_incomplete": True,
            },
        )

        responseEquals(response, status.HTTP_201_CREATED)

    @patch("baseapp_payments.views.StripeService.list_subscriptions")
    @patch("baseapp_payments.views.StripeService.retrieve_price")
    def test_resubscribing_to_the_same_product_is_still_rejected(
        self, mock_retrieve_price, mock_list_subscriptions, user_client
    ):
        """The duplicate check has to keep working across both shapes."""
        mock_retrieve_price.return_value = {"id": "price_new", "product": {"id": "prod_same"}}
        mock_list_subscriptions.return_value = stripe_list(
            [
                {
                    "id": "sub_existing",
                    "status": "active",
                    "items": {"data": [{"price": {"id": "price_old", "product": "prod_same"}}]},
                }
            ]
        )
        customer = CustomerFactory(entity=user_client.user.profile, remote_customer_id="cus_123")
        response = user_client.post(
            reverse(self.viewname),
            data={"entity_id": customer.entity.relay_id, "price_id": "price_new"},
        )

        responseEquals(response, status.HTTP_400_BAD_REQUEST)
