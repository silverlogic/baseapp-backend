from unittest.mock import patch

import pytest
import stripe

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


def test_retrieve_product_invalid_request_error():
    with patch("baseapp_payments.utils.stripe.Product.retrieve") as mock_retrieve:
        mock_retrieve.side_effect = stripe.error.InvalidRequestError("No such product", "id")
        result = StripeService().retrieve_product("prod_invalid")
    assert result is None


def test_retrieve_product_stripe_error():
    with patch("baseapp_payments.utils.stripe.Product.retrieve") as mock_retrieve:
        mock_retrieve.side_effect = stripe.error.StripeError("Stripe API error")
        result = StripeService().retrieve_product("prod_123")
    assert result is None


def test_get_payment_intent_unexpected_invalid_request_error():
    from baseapp_payments.utils import PaymentIntendNotFound

    with patch("baseapp_payments.utils.stripe.PaymentIntent.retrieve") as mock_retrieve:
        mock_retrieve.side_effect = stripe.error.InvalidRequestError("Some other error", "id")
        with pytest.raises(PaymentIntendNotFound):
            StripeService().get_payment_intent("pi_invalid")


def test_retrieve_price_not_found():
    with patch("baseapp_payments.utils.stripe.Price.retrieve") as mock_retrieve:
        mock_retrieve.side_effect = stripe.error.InvalidRequestError(
            "No such price: price_123", "id"
        )
        result = StripeService().retrieve_price("price_123")
    assert result is None


def test_retrieve_price_invalid_request():
    with patch("baseapp_payments.utils.stripe.Price.retrieve") as mock_retrieve:
        mock_retrieve.side_effect = stripe.error.InvalidRequestError("Invalid request", "id")
        result = StripeService().retrieve_price("price_invalid")
    assert result is None


def test_retrieve_price_stripe_error():
    with patch("baseapp_payments.utils.stripe.Price.retrieve") as mock_retrieve:
        mock_retrieve.side_effect = stripe.error.StripeError("Stripe API error")
        result = StripeService().retrieve_price("price_123")
    assert result is None


def test_update_subscription_invalid_request_not_found():
    from baseapp_payments.utils import SubscriptionNotFound

    with patch("baseapp_payments.utils.stripe.Subscription.modify") as mock_modify:
        mock_modify.side_effect = stripe.error.InvalidRequestError(
            "No such subscription: sub_123", "id"
        )
        with pytest.raises(SubscriptionNotFound):
            StripeService().update_subscription("sub_123")


def test_update_subscription_invalid_request_other():
    with patch("baseapp_payments.utils.stripe.Subscription.modify") as mock_modify:
        mock_modify.side_effect = stripe.error.InvalidRequestError("Invalid request", "id")
        with pytest.raises(stripe.error.InvalidRequestError):
            StripeService().update_subscription("sub_123")
