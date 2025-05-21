from unittest.mock import patch

import pytest

from baseapp_payments.utils import StripeService

from .factories import CustomerFactory, UserFactory

mock_customer = {"id": "cus_123"}


@pytest.mark.django_db
def test_check_customer_id_for_user_success():
    with patch("baseapp_payments.utils.StripeService.retrieve_customer") as mock_retrieve_customer:
        mock_retrieve_customer.return_value = mock_customer
        user = UserFactory()
        CustomerFactory(entity=user.profile, remote_customer_id="cus_123")
        stripe_service = StripeService()
        result = stripe_service.checkCustomerIdForUser("cus_123", user)
        assert result is True


@pytest.mark.django_db
def test_check_customer_id_for_user_customer_not_found():
    with patch("baseapp_payments.utils.StripeService.retrieve_customer") as mock_retrieve_customer:
        mock_retrieve_customer.return_value = None
        user = UserFactory()
        CustomerFactory(entity=user.profile, remote_customer_id="cus_123")
        stripe_service = StripeService()
        result = stripe_service.checkCustomerIdForUser("non_existent_cus_123", user)
        assert result is False


@pytest.mark.django_db
def test_retrieve_customer_by_email():
    with patch("baseapp_payments.utils.StripeService.retrieve_customer") as mock_retrieve_customer:
        mock_retrieve_customer.return_value = mock_customer
        user = UserFactory()
        CustomerFactory(entity=user.profile, remote_customer_id="cus_123")
        stripe_service = StripeService()
        result = stripe_service.retrieve_customer(email=user.email)
        assert result == mock_customer


@pytest.mark.django_db
def test_retrieve_customer_by_customer_id():
    with patch("baseapp_payments.utils.StripeService.retrieve_customer") as mock_retrieve_customer:
        mock_retrieve_customer.return_value = mock_customer
        user = UserFactory()
        CustomerFactory(entity=user.profile, remote_customer_id="cus_123")
        stripe_service = StripeService()
        result = stripe_service.retrieve_customer(customer_id="cus_123")
        assert result == mock_customer
