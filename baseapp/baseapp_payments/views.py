import logging

from django.conf import settings
from rest_framework import viewsets
from rest_framework.exceptions import NotFound
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Customer, Subscription
from .serializers import (
    StripeCustomerSerializer,
    StripeSubscriptionSerializer,
    StripeWebhookSerializer,
)
from .utils import StripeService, StripeWebhookHandler

logger = logging.getLogger(__name__)


class StripeSubscriptionViewset(
    viewsets.GenericViewSet,
    viewsets.mixins.RetrieveModelMixin,
    viewsets.mixins.DestroyModelMixin,
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

    def delete(self, request):
        remote_subscription_id = request.data.get("remote_subscription_id")
        customer = Customer.objects.filter(entity_id=self.request.user.id).first()
        if not customer:
            raise NotFound("Customer does not exist.")
        try:
            subscription = Subscription.objects.filter(
                remote_subscription_id=remote_subscription_id,
                remote_customer_id=customer.remote_customer_id,
            )
            if not subscription.exists():
                raise NotFound
            StripeService().delete_subscription(remote_subscription_id)
            subscription.delete()
            return Response({"status": "success"}, status=200)
        except NotFound:
            return Response({"error": "Subscription not found"}, status=404)
        except Exception as e:
            logger.exception(e)
            return Response({"error": "Error deleting subscription"}, status=500)


class StripeWebhookViewset(viewsets.GenericViewSet):
    serializer_class = StripeWebhookSerializer
    permission_classes = []

    def create(self, request):
        endpoint_secret = settings.STRIPE_WEBHOOK_SECRET
        response = StripeWebhookHandler().webhook_handler(request, endpoint_secret)
        return response


class StripeProductViewset(viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated]

    def list(self, request):
        products = StripeService().list_products()
        return Response(products, status=200)


class StripeCustomerViewset(viewsets.GenericViewSet):
    serializer_class = StripeCustomerSerializer
    queryset = Customer.objects.all()
    permission_classes = [IsAuthenticated]
    lookup_field = "remote_customer_id"

    def get_queryset(self):
        return Customer.objects.all()

    def list(self, request):
        remote_customer_id = request.query_params.get("remote_customer_id")
        if not remote_customer_id:
            raise NotFound("Customer ID not provided")
        customer = StripeService().retrieve_customer(remote_customer_id)
        if not customer:
            raise NotFound("Customer not found")
        return Response(customer, status=200)

    def create(self, request):
        serializer = StripeCustomerSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=201)

    def retrieve(self, request, remote_customer_id=None):
        customer = StripeService().retrieve_customer(remote_customer_id)
        if not customer:
            raise NotFound("Customer not found")
        return Response(customer, status=200)
