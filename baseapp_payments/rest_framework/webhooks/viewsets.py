from django.conf import settings
from rest_framework import viewsets

from baseapp_payments.utils import StripeWebhookHandler

from .serializers import StripeWebhookSerializer


class StripeWebhookViewSet(viewsets.GenericViewSet):
    serializer_class = StripeWebhookSerializer
    permission_classes = []

    def create(self, request):
        endpoint_secret = settings.STRIPE_WEBHOOK_SECRET
        response = StripeWebhookHandler().webhook_handler(request, endpoint_secret)
        return response
