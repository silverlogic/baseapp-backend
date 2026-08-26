"""Behaviour of the `StripeService` wrappers.

These are thin, but the interesting part is what they do with failures: which
Stripe error becomes which local exception, and which ones are answered with
`None` instead of raising. That translation is what callers depend on, so it is
what is pinned here.
"""

from unittest.mock import patch

import pytest
import stripe

from baseapp_payments.utils import (
    CustomerCreationError,
    CustomerNotFound,
    CustomerUpdateError,
    PaymentIntendNotFound,
    PaymentMethodDeletionError,
    PaymentMethodNotFound,
    PaymentMethodUpdateError,
    PriceRetrievalError,
    SetupIntentCreationError,
    StripeService,
    SubscriptionCreationError,
    SubscriptionNotFound,
)

from .helpers import stripe_list


class _AttrDict(dict):
    """Stripe objects expose keys as attributes; the code under test uses both."""

    __getattr__ = dict.__getitem__


def _invalid_request(message):
    return stripe.error.InvalidRequestError(message, param=None)


@pytest.fixture
def service():
    return StripeService()


class TestCustomerCalls:
    def test_create_customer_translates_failures(self, service):
        with patch("baseapp_payments.utils.stripe.Customer.create") as mock_create:
            mock_create.side_effect = Exception("boom")
            with pytest.raises(CustomerCreationError):
                service.create_customer(email="a@example.com")

    def test_retrieve_customer_by_id(self, service):
        with patch("baseapp_payments.utils.stripe.Customer.retrieve") as mock_retrieve:
            mock_retrieve.return_value = {"id": "cus_1"}
            assert service.retrieve_customer("cus_1") == {"id": "cus_1"}

    def test_unknown_customer_is_none_not_an_error(self, service):
        with patch("baseapp_payments.utils.stripe.Customer.retrieve") as mock_retrieve:
            mock_retrieve.side_effect = _invalid_request("No such customer: cus_x")
            assert service.retrieve_customer("cus_x") is None

    def test_other_invalid_requests_still_raise(self, service):
        """A malformed request is not the same as a missing customer; answering
        `None` for both would make a real failure look like an empty result."""
        with patch("baseapp_payments.utils.stripe.Customer.retrieve") as mock_retrieve:
            mock_retrieve.side_effect = _invalid_request("Invalid expand value")
            with pytest.raises(CustomerNotFound):
                service.retrieve_customer("cus_x")

    def test_lookup_by_email_returns_the_first_match(self, service):
        with patch("baseapp_payments.utils.stripe.Customer.search") as mock_search:
            mock_search.return_value = stripe_list([{"id": "cus_first"}, {"id": "cus_second"}])
            mock_search.return_value.data = [{"id": "cus_first"}, {"id": "cus_second"}]
            assert service.retrieve_customer(email="a@example.com") == {"id": "cus_first"}

    def test_lookup_by_email_escapes_the_query(self, service):
        """The address reaches Stripe's query DSL, so a quote in it must not be
        able to close the string it is embedded in."""
        with patch("baseapp_payments.utils.stripe.Customer.search") as mock_search:
            mock_search.return_value = stripe_list([])
            mock_search.return_value.data = []
            service.retrieve_customer(email="a'b@example.com")
            assert mock_search.call_args.kwargs["query"] == "email:'a\\'b@example.com'"

    def test_lookup_by_email_with_no_match(self, service):
        with patch("baseapp_payments.utils.stripe.Customer.search") as mock_search:
            mock_search.return_value = stripe_list([])
            mock_search.return_value.data = []
            assert service.retrieve_customer(email="nobody@example.com") is None

    def test_update_customer_translates_failures(self, service):
        with patch("baseapp_payments.utils.stripe.Customer.modify") as mock_modify:
            mock_modify.side_effect = Exception("boom")
            with pytest.raises(CustomerUpdateError):
                service.update_customer("cus_1", email="b@example.com")

    def test_delete_unknown_customer_is_none(self, service):
        with patch("baseapp_payments.utils.stripe.Customer.delete") as mock_delete:
            mock_delete.side_effect = _invalid_request("No such customer: cus_x")
            assert service.delete_customer("cus_x") is None


class TestSubscriptionCalls:
    def test_create_subscription_translates_failures(self, service):
        with patch("baseapp_payments.utils.stripe.Subscription.create") as mock_create:
            mock_create.side_effect = Exception("boom")
            with pytest.raises(SubscriptionCreationError):
                service.create_subscription("cus_1", "price_1")

    def test_retrieve_unknown_subscription_is_none(self, service):
        with patch("baseapp_payments.utils.stripe.Subscription.retrieve") as mock_retrieve:
            mock_retrieve.side_effect = Exception("No such subscription: sub_x")
            assert service.retrieve_subscription("sub_x") is None

    def test_retrieve_subscription_forwards_stripe_kwargs(self, service):
        """The read serializer resolves client_secret and product out of expanded
        fields, so `expand` has to reach Stripe rather than be swallowed."""
        with (
            patch("baseapp_payments.utils.stripe.Subscription.retrieve") as mock_retrieve,
            patch("baseapp_payments.utils.stripe.Invoice.create_preview") as mock_preview,
        ):
            mock_retrieve.return_value = {"id": "sub_1", "customer": "cus_1"}
            mock_preview.side_effect = Exception("no upcoming invoice")
            service.retrieve_subscription("sub_1", expand=["latest_invoice.payment_intent"])
            assert mock_retrieve.call_args.kwargs["expand"] == ["latest_invoice.payment_intent"]

    def test_retrieve_subscription_survives_a_missing_upcoming_invoice(self, service):
        with (
            patch("baseapp_payments.utils.stripe.Subscription.retrieve") as mock_retrieve,
            patch("baseapp_payments.utils.stripe.Invoice.create_preview") as mock_preview,
        ):
            mock_retrieve.return_value = {"id": "sub_1", "customer": "cus_1"}
            mock_preview.side_effect = Exception("nothing upcoming")
            assert service.retrieve_subscription("sub_1")["id"] == "sub_1"

    def test_list_subscriptions_for_an_unknown_customer_pages_as_empty(self, service):
        """A stale remote_customer_id must not crash callers that page the result."""
        with patch("baseapp_payments.utils.stripe.Subscription.list") as mock_list:
            mock_list.side_effect = Exception("No such customer: cus_x")
            result = service.list_subscriptions("cus_x")
            assert list(result.auto_paging_iter()) == []

    def test_list_subscriptions_translates_other_failures(self, service):
        with patch("baseapp_payments.utils.stripe.Subscription.list") as mock_list:
            mock_list.side_effect = Exception("boom")
            with pytest.raises(SubscriptionNotFound):
                service.list_subscriptions("cus_1")

    def test_delete_unknown_subscription_is_none(self, service):
        with patch("baseapp_payments.utils.stripe.Subscription.cancel") as mock_cancel:
            mock_cancel.side_effect = Exception("No such subscription: sub_x")
            assert service.delete_subscription("sub_x") is None


class TestPaymentMethodCalls:
    def test_retrieve_payment_method_translates_failures(self, service):
        with patch("baseapp_payments.utils.stripe.PaymentMethod.retrieve") as mock_retrieve:
            mock_retrieve.side_effect = Exception("boom")
            with pytest.raises(PaymentMethodNotFound):
                service.retrieve_payment_method("pm_1")

    def test_list_payment_methods_translates_failures(self, service):
        with patch("baseapp_payments.utils.stripe.PaymentMethod.list") as mock_list:
            mock_list.side_effect = Exception("boom")
            with pytest.raises(CustomerNotFound):
                service.list_payment_methods("cus_1")

    def test_belongs_to_finds_a_card_past_the_first_page(self, service):
        with patch("baseapp_payments.utils.StripeService.list_payment_methods") as mock_list:
            mock_list.return_value = stripe_list([{"id": "pm_page_two"}])
            assert service.payment_method_belongs_to("pm_page_two", "cus_1") is True

    def test_belongs_to_rejects_a_card_of_another_customer(self, service):
        with patch("baseapp_payments.utils.StripeService.list_payment_methods") as mock_list:
            mock_list.return_value = stripe_list([{"id": "pm_mine"}])
            assert service.payment_method_belongs_to("pm_theirs", "cus_1") is False

    def test_belongs_to_is_false_without_both_ids(self, service):
        assert service.payment_method_belongs_to(None, "cus_1") is False
        assert service.payment_method_belongs_to("pm_1", None) is False

    def test_belongs_to_is_false_for_an_unknown_customer(self, service):
        with patch("baseapp_payments.utils.StripeService.list_payment_methods") as mock_list:
            mock_list.side_effect = CustomerNotFound("gone")
            assert service.payment_method_belongs_to("pm_1", "cus_x") is False

    def test_update_payment_method_translates_failures(self, service):
        with patch("baseapp_payments.utils.stripe.PaymentMethod.modify") as mock_modify:
            mock_modify.side_effect = Exception("boom")
            with pytest.raises(PaymentMethodUpdateError):
                service.update_payment_method("pm_1", billing_details={})

    def test_delete_payment_method_clears_the_default_only_when_asked(self, service):
        with (
            patch("baseapp_payments.utils.stripe.PaymentMethod.detach") as mock_detach,
            patch("baseapp_payments.utils.stripe.Customer.modify") as mock_modify,
        ):
            service.delete_payment_method("pm_1", "cus_1", is_default=False)
            mock_modify.assert_not_called()
            mock_detach.assert_called_once_with("pm_1")

            service.delete_payment_method("pm_1", "cus_1", is_default=True)
            assert mock_modify.call_args.kwargs["invoice_settings"] == {
                "default_payment_method": None
            }

    def test_delete_payment_method_translates_failures(self, service):
        with patch("baseapp_payments.utils.stripe.PaymentMethod.detach") as mock_detach:
            mock_detach.side_effect = Exception("boom")
            with pytest.raises(PaymentMethodDeletionError):
                service.delete_payment_method("pm_1", "cus_1")

    def test_get_customer_payment_methods_flags_the_default(self, service):
        with (
            patch("baseapp_payments.utils.StripeService.retrieve_customer") as mock_retrieve,
            patch("baseapp_payments.utils.StripeService.list_payment_methods") as mock_list,
        ):
            mock_retrieve.return_value = {
                "invoice_settings": {"default_payment_method": "pm_default"}
            }
            first = _AttrDict(id="pm_default")
            second = _AttrDict(id="pm_other")
            mock_list.return_value = stripe_list([first, second])
            result = service.get_customer_payment_methods("cus_1")
            assert result[0]["is_default"] is True
            assert "is_default" not in result[1]

    def test_get_customer_payment_methods_for_an_unknown_customer(self, service):
        with patch("baseapp_payments.utils.StripeService.retrieve_customer") as mock_retrieve:
            mock_retrieve.return_value = None
            with pytest.raises(CustomerNotFound):
                service.get_customer_payment_methods("cus_x")


class TestIntentAndPriceCalls:
    def test_create_setup_intent_translates_failures(self, service):
        with patch("baseapp_payments.utils.stripe.SetupIntent.create") as mock_create:
            mock_create.side_effect = Exception("boom")
            with pytest.raises(SetupIntentCreationError):
                service.create_setup_intent("cus_1")

    def test_get_payment_intent_translates_failures(self, service):
        with patch("baseapp_payments.utils.stripe.PaymentIntent.retrieve") as mock_retrieve:
            mock_retrieve.side_effect = Exception("boom")
            with pytest.raises(PaymentIntendNotFound):
                service.get_payment_intent("pi_1")

    def test_retrieve_price_translates_failures(self, service):
        with patch("baseapp_payments.utils.stripe.Price.retrieve") as mock_retrieve:
            mock_retrieve.side_effect = Exception("boom")
            with pytest.raises(PriceRetrievalError):
                service.retrieve_price("price_1")


class TestListingCalls:
    def test_list_products_defaults_to_active_and_pages(self, service):
        with patch("baseapp_payments.utils.stripe.Product.list") as mock_list:
            mock_list.return_value = stripe_list([{"id": "prod_1"}])
            service.list_products()
            assert mock_list.call_args.kwargs["active"] is True

    def test_list_invoices_returns_a_pageable_result(self, service):
        with patch("baseapp_payments.utils.stripe.Invoice.list") as mock_list:
            mock_list.return_value = stripe_list([{"id": "in_1"}])
            assert list(service.list_invoices("cus_1").auto_paging_iter()) == [{"id": "in_1"}]
