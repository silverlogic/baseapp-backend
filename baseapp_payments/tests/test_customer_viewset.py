from unittest.mock import MagicMock, patch

import pytest
import swapper
from django.contrib.contenttypes.models import ContentType
from django.db import IntegrityError, transaction
from django.urls import reverse
from rest_framework import status

from baseapp_core.graphql.utils import get_obj_relay_id
from baseapp_core.tests.fixtures import Client
from baseapp_core.tests.helpers import responseEquals
from baseapp_payments.tests.factories import CustomerFactory, SubscriptionFactory
from baseapp_profiles.tests.factories import ProfileFactory

pytestmark = pytest.mark.django_db


Profile = swapper.load_model("profiles", "Profile")
Customer = swapper.load_model("baseapp_payments", "Customer")


class TestCustomerRetrieveView:
    viewname = "v1:customers-detail"

    def test_anon_user_cannot_get_customer(self, client: Client) -> None:
        response = client.get(reverse(self.viewname, kwargs={"entity_id": 1}))
        responseEquals(response, status.HTTP_401_UNAUTHORIZED)

    @patch("baseapp_payments.views.StripeService.list_subscriptions")
    def test_user_can_get_customer(
        self, mock_list_subscriptions: MagicMock, user_client: Client
    ) -> None:
        mock_list_subscriptions.return_value.data = []
        customer = CustomerFactory(entity=user_client.user.profile, remote_customer_id="cus_123")
        response = user_client.get(reverse(self.viewname, kwargs={"entity_id": customer.entity_id}))
        responseEquals(response, status.HTTP_200_OK)

    @patch("baseapp_payments.views.StripeService.list_subscriptions")
    def test_user_can_get_customer_me(
        self, mock_list_subscriptions: MagicMock, user_client: Client
    ) -> None:
        mock_list_subscriptions.return_value.data = []
        customer = CustomerFactory(entity=user_client.user.profile, remote_customer_id="cus_123")
        response = user_client.get(reverse(self.viewname, kwargs={"entity_id": "me"}))
        responseEquals(response, status.HTTP_200_OK)
        assert response.data["remote_customer_id"] == customer.remote_customer_id


class TestCustomerCreateView:
    viewname = "v1:customers-list"

    def test_anon_user_cannot_create_customer(self, client: Client) -> None:
        response = client.post(reverse(self.viewname, kwargs={}))
        responseEquals(response, status.HTTP_401_UNAUTHORIZED)

    @patch("baseapp_payments.views.StripeService.list_subscriptions")
    @patch("baseapp_payments.views.StripeService.create_customer")
    def test_user_can_create_customer(
        self,
        mock_create_customer: MagicMock,
        mock_list_subscriptions: MagicMock,
        user_client: Client,
    ) -> None:
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


class TestCustomerMeWithoutACustomer:
    viewname = "v1:customers-detail"

    def test_me_is_404_when_the_user_has_no_customer(self, user_client: Client) -> None:
        """The frontend reads this 404 as "create one"; it used to be a 500."""
        response = user_client.get(reverse(self.viewname, kwargs={"entity_id": "me"}))

        responseEquals(response, status.HTTP_404_NOT_FOUND)


class TestCustomerUniqueness:
    def test_an_entity_cannot_have_two_customers(self) -> None:
        """One row per billed entity.

        The constraint was dropped incidentally by the invoice-endpoint commit (#305).
        Without it two concurrent requests for the same profile each insert a row, and
        each row goes on to get its own Stripe customer - so the profile is billed
        through whichever one a later query happens to return first.
        """
        profile = ProfileFactory()
        CustomerFactory(entity=profile)

        with pytest.raises(IntegrityError), transaction.atomic():
            CustomerFactory(entity=profile)


class TestSubscriptionUniqueness:
    def test_a_stripe_subscription_id_cannot_repeat(self) -> None:
        """One row per Stripe subscription, across all customers.

        StripeSubscriptionViewset resolves with lookup_field="remote_subscription_id"
        and the webhook handler filters on it alone, so a duplicate is
        MultipleObjectsReturned on read and a multi-row delete on cancellation. The
        pair this replaces, (remote_customer_id, remote_subscription_id), allowed the
        same Stripe id under two customers and so never ruled that out.
        """
        SubscriptionFactory(remote_subscription_id="sub_1")

        with pytest.raises(IntegrityError), transaction.atomic():
            SubscriptionFactory(remote_subscription_id="sub_1")


class TestCustomerEntityTypeFallback:
    def test_entity_type_is_resolved_from_the_configured_label(self) -> None:
        """STRIPE_CUSTOMER_ENTITY_MODEL is a dotted label, not a class.

        get_for_model reads model._meta, so handing it the string raised AttributeError
        and the except turned that into a misleading configuration error - the fallback
        could never succeed.
        """
        profile = ProfileFactory()
        customer = Customer(entity_id=profile.id, remote_customer_id="cus_fallback")
        customer.save()

        assert customer.entity_type == ContentType.objects.get_for_model(Profile)
