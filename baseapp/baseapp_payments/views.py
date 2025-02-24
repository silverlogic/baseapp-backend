import logging

import swapper

from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from .serializers import (
    StripeSubscriptionSerializer,
    StripeCustomerSerializer,
)
from django.db import transaction
from .utils import StripeService, StripeWebhookHandler
from .models import Subscription
from django.core.exceptions import ObjectDoesNotExist
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import NotFound

logger = logging.getLogger(__name__)


class StripePaymentsViewset(
    viewsets.GenericViewSet,
    viewsets.mixins.RetrieveModelMixin,
):
    serializer_class = StripeSubscriptionSerializer
    queryset = Subscription.objects.all()
    permission_classes = [IsAuthenticated]
    lookup_field = "remote_subscription_id"

    def get_queryset(self):
        return Subscription.objects.all()

    def create(self, request):
        serializer = self.serializer_class(data=request.data)
        if serializer.is_valid():
            return Response(serializer.data, status=201)
        return Response(serializer.errors, status=400)

    def retrieve(self, request, remote_subscription_id=None):
        subscription = StripeService().retrieve_subscription(remote_subscription_id)
        if not subscription:
            raise NotFound("Subscription not found")
        return Response(subscription, status=200)

    @transaction.atomic
    def delete(self, request):
        remote_subscription_id = request.data.get("remote_subscription_id")
        try:
            StripeService().delete_subscription(remote_subscription_id)
            Subscription.objects.get(remote_subscription_id=remote_subscription_id).delete()
            return Response({"status": "success"}, status=200)
        except ObjectDoesNotExist:
            return Response({"error": "Subscription not found"}, status=404)
        except Exception as e:
            logger.exception(e)
            return Response({"error": "Error deleting subscription"}, status=500)

    @action(detail=False, methods=["post", "get"])
    def customer(self, request):
        if request.method == "GET":
            remote_customer_id = request.query_params.get("remote_customer_id")
            if not remote_customer_id:
                raise NotFound("Customer ID not provided")
            customer = StripeService().retrieve_customer(remote_customer_id)
            if not customer:
                raise NotFound("Customer not found")
            return Response(customer, status=200)
        elif request.method == "POST":
            serializer = StripeCustomerSerializer(data=request.data, context={"request": request})
            serializer.is_valid(raise_exception=True)
            serializer.save()
            return Response(serializer.data, status=201)

    @action(detail=False, methods=["get"])
    def products(self, request):
        products = StripeService().list_products()
        return Response(products, status=200)

    @action(detail=False, methods=["post"], permission_classes=[])
    def webhook(self, request):
        endpoint_secret = "whsec_4796e64cf916843594eafb014315f076d2cce2c00c4b409a13ae8d0db1ab83f1"
        response = StripeWebhookHandler().webhook_handler(request, endpoint_secret)
        return response
