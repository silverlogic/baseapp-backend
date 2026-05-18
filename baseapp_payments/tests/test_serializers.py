from unittest.mock import MagicMock, patch

import pytest
from rest_framework.exceptions import ValidationError

from baseapp_payments.serializers import (
    StripePaymentMethodSerializer,
    StripeSubscriptionPatchSerializer,
    StripeSubscriptionSerializer,
)


def test_subscription_create_logs_payment_method_update_failure():
    with (
        patch("baseapp_payments.serializers.StripeService.update_payment_method") as mock_update,
        patch("baseapp_payments.serializers.StripeService.create_subscription") as mock_create_sub,
    ):
        mock_update.side_effect = Exception("PM update failed")
        mock_create_sub.return_value = MagicMock(id="sub_123")

        serializer = StripeSubscriptionSerializer()
        result = serializer.create(
            {
                "remote_customer_id": "cus_123",
                "price_id": "price_123",
                "payment_method_id": "pm_123",
                "billing_details": {"name": "Test"},
                "allow_incomplete": False,
            }
        )
    assert result == {"remote_subscription_id": "sub_123"}


def test_subscription_patch_validate_payment_method_logs_on_exception():
    with (
        patch("baseapp_payments.serializers.StripeService.list_payment_methods") as mock_list,
        patch("baseapp_payments.serializers.StripeService.checkCustomerIdForUser") as mock_check,
    ):
        mock_list.side_effect = Exception("API error")
        mock_check.return_value = True

        mock_request = MagicMock()
        mock_request.user = MagicMock()

        serializer = StripeSubscriptionPatchSerializer(
            data={
                "remote_customer_id": "cus_123",
                "default_payment_method": "pm_123",
            },
            context={"request": mock_request},
        )
        assert not serializer.is_valid()
        assert "default_payment_method" in serializer.errors


def test_payment_method_create_setup_intent_failure():
    with patch("baseapp_payments.serializers.StripeService.create_setup_intent") as mock_create:
        mock_create.side_effect = Exception("Setup intent failed")

        serializer = StripePaymentMethodSerializer()
        with pytest.raises(ValidationError):
            serializer.create({"customer_id": "cus_123"})
