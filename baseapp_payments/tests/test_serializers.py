from unittest.mock import MagicMock, patch

import pytest
from rest_framework.exceptions import ValidationError

from baseapp_payments.serializers import (
    StripePaymentMethodSerializer,
    StripeSubscriptionSerializer,
)

pytestmark = pytest.mark.django_db


def test_subscription_create_logs_payment_method_update_failure() -> None:
    """A failing billing-details update must not abort the subscription."""
    customer = MagicMock(remote_customer_id="cus_123")
    with (
        patch("baseapp_payments.serializers.StripeService.update_payment_method") as mock_update,
        patch("baseapp_payments.serializers.StripeService.create_subscription") as mock_create_sub,
        patch.object(StripeSubscriptionSerializer, "validate_create") as mock_validate,
        patch("baseapp_payments.serializers.Subscription.objects.create") as mock_row,
    ):
        mock_update.side_effect = Exception("PM update failed")
        mock_create_sub.return_value = {"id": "sub_123", "status": "active"}
        mock_validate.return_value = {
            "customer": customer,
            "price_id": "price_123",
            "payment_method_id": "pm_123",
            "billing_details": {"name": "Test"},
            "allow_incomplete": False,
        }

        result = StripeSubscriptionSerializer().create({})

    assert result == {"id": "sub_123", "status": "active"}
    mock_row.assert_called_once()


def test_payment_method_create_setup_intent_failure() -> None:
    """A failed setup intent has to surface, not return None and read as success."""
    with patch("baseapp_payments.serializers.StripeService.create_setup_intent") as mock_create:
        mock_create.side_effect = Exception("Setup intent failed")

        serializer = StripePaymentMethodSerializer(
            context={"customer": MagicMock(remote_customer_id="cus_123")}
        )
        with pytest.raises(ValidationError):
            serializer.create({})
