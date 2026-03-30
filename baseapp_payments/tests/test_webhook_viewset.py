import json
from unittest.mock import patch

import pytest
import stripe
from django.urls import reverse
from rest_framework import status

pytestmark = pytest.mark.django_db


class TestWebhookCreateView:
    viewname = "v1:webhooks-stripe-list"

    def _post_webhook(self, client, payload=None, signature="test_sig"):
        if payload is None:
            payload = {"id": "evt_123", "object": "event"}
        return client.post(
            reverse(self.viewname),
            data=json.dumps(payload),
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE=signature,
        )

    @patch("baseapp_payments.utils.stripe.Webhook.construct_event")
    def test_valid_unhandled_event_returns_200(self, mock_construct_event, client):
        mock_construct_event.return_value = {
            "type": "payment_intent.succeeded",
            "data": {"object": {}},
        }
        response = self._post_webhook(client)
        assert response.status_code == status.HTTP_200_OK
        assert json.loads(response.content) == {"status": "success"}

    @patch("baseapp_payments.utils.stripe.Webhook.construct_event")
    def test_invalid_payload_returns_400(self, mock_construct_event, client):
        mock_construct_event.side_effect = ValueError("Invalid payload")
        response = self._post_webhook(client)
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    @patch("baseapp_payments.utils.stripe.Webhook.construct_event")
    def test_invalid_signature_returns_400(self, mock_construct_event, client):
        mock_construct_event.side_effect = stripe.error.SignatureVerificationError(
            "Invalid signature", "test_sig"
        )
        response = self._post_webhook(client)
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    @patch("baseapp_payments.utils.stripe.Webhook.construct_event")
    def test_handled_event_customer_deleted_returns_200(self, mock_construct_event, client):
        mock_construct_event.return_value = {
            "type": "customer.deleted",
            "data": {"object": {"id": "cus_nonexistent"}},
        }
        response = self._post_webhook(client)
        assert response.status_code == status.HTTP_200_OK
