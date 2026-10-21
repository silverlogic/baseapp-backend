"""A raw entity pk must never be read as a relay id.

Every 4- and 8-digit number is valid base64, and many decode to valid UTF-8 - "1400"
decodes to U+05CD followed by "4". ``get_pk_from_relay_id`` answers that decoded text
for anything without a ``Type:`` prefix, so a raw pk in one of those ranges came back as
a non-empty "pk" and the lookup missed the entity it named. Which tests failed depended
on where the profile sequence stood when they ran, so these pin the pk instead.
"""

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest
from django.urls import reverse
from graphql_relay import to_global_id
from rest_framework import status

from baseapp_core.graphql import get_pk_from_relay_id
from baseapp_core.tests.fixtures import Client
from baseapp_core.tests.helpers import responseEquals
from baseapp_payments.tests.factories import CustomerFactory
from baseapp_payments.tests.helpers import stripe_list
from baseapp_payments.utils import get_entity_pk_from_relay_id
from baseapp_profiles.tests.factories import ProfileFactory

if TYPE_CHECKING:
    from baseapp_payments.models import BaseCustomer

# Decodes as base64 to valid UTF-8, and is far above any pk the suite's sequences reach.
AMBIGUOUS_PK = 14001400


def test_the_pinned_pk_is_one_get_pk_from_relay_id_misreads() -> None:
    # Guards the premise: if this stops holding, the tests below prove nothing.
    assert get_pk_from_relay_id(str(AMBIGUOUS_PK))


@pytest.mark.parametrize(
    "value",
    [
        str(AMBIGUOUS_PK),
        "1400",
        "1419",
        "7",
        "not-a-relay-id",
        "",
        to_global_id("Profile", "abc"),
        to_global_id("Profile", "0"),
    ],
)
def test_values_that_are_not_relay_ids_of_an_entity_resolve_to_none(value: str) -> None:
    assert get_entity_pk_from_relay_id(value) is None


@pytest.mark.django_db
def test_a_relay_id_resolves_to_its_pk() -> None:
    profile = ProfileFactory(pk=AMBIGUOUS_PK)

    assert get_entity_pk_from_relay_id(profile.relay_id) == AMBIGUOUS_PK


@pytest.mark.django_db
class TestRawPkThatDecodesAsBase64:
    @pytest.fixture
    def customer(self, user_client: Client) -> "BaseCustomer":
        profile = ProfileFactory(pk=AMBIGUOUS_PK, owner=user_client.user)
        return CustomerFactory(entity=profile, remote_customer_id="cus_ambiguous")

    @patch("baseapp_payments.serializers.StripeService.list_subscriptions")
    def test_customer_is_found_by_raw_pk(
        self, mock_list_subscriptions: MagicMock, user_client: Client, customer: "BaseCustomer"
    ) -> None:
        mock_list_subscriptions.return_value = stripe_list([])
        response = user_client.get(
            reverse("v1:customers-detail", kwargs={"entity_id": AMBIGUOUS_PK})
        )
        responseEquals(response, status.HTTP_200_OK)
        assert response.data["remote_customer_id"] == "cus_ambiguous"

    @patch("baseapp_payments.views.StripeService.retrieve_customer")
    @patch("baseapp_payments.views.StripeService.get_customer_payment_methods")
    def test_payment_methods_are_found_by_raw_pk(
        self,
        mock_get_customer_payment_methods: MagicMock,
        mock_retrieve_customer: MagicMock,
        user_client: Client,
        customer: "BaseCustomer",
    ) -> None:
        mock_retrieve_customer.return_value = {"id": "cus_ambiguous"}
        mock_get_customer_payment_methods.return_value = [{"id": "pm_1"}]
        response = user_client.get(
            reverse("v1:customers-payment-methods", kwargs={"entity_id": AMBIGUOUS_PK})
        )
        responseEquals(response, status.HTTP_200_OK)
        assert response.json() == [{"id": "pm_1", "is_default": False}]

    def test_subscription_list_by_raw_pk_is_not_found_rather_than_an_error(
        self, user_client: Client, customer: "BaseCustomer"
    ) -> None:
        # This route takes relay ids only. The decoded garbage used to reach the integer
        # entity_id column and raise.
        response = user_client.get(
            reverse("v1:subscriptions-list"), data={"entity_id": str(AMBIGUOUS_PK)}
        )
        responseEquals(response, status.HTTP_404_NOT_FOUND)

    @patch("baseapp_payments.views.StripeService.list_subscriptions")
    def test_subscription_list_by_relay_id_still_works(
        self, mock_list_subscriptions: MagicMock, user_client: Client, customer: "BaseCustomer"
    ) -> None:
        mock_list_subscriptions.return_value = stripe_list([])
        response = user_client.get(
            reverse("v1:subscriptions-list"), data={"entity_id": customer.entity.relay_id}
        )
        responseEquals(response, status.HTTP_200_OK)
