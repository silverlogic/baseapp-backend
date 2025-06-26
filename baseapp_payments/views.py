import logging

import swapper
from django.conf import settings
from rest_framework import viewsets
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Subscription
from .permissions import HasCustomerPermissions
from .serializers import (
    StripeCustomerSerializer,
    StripeInvoiceSerializer,
    StripePaymentMethodSerializer,
    StripeProductSerializer,
    StripeSubscriptionPatchSerializer,
    StripeSubscriptionSerializer,
    StripeWebhookSerializer,
)
from .utils import StripeService, StripeWebhookHandler, get_customer

logger = logging.getLogger(__name__)

Customer = swapper.load_model("baseapp_payments", "Customer")


class StripeSubscriptionViewset(
    viewsets.GenericViewSet,
    viewsets.mixins.RetrieveModelMixin,
    viewsets.mixins.DestroyModelMixin,
    viewsets.mixins.UpdateModelMixin,
):
    serializer_class = StripeSubscriptionSerializer
    queryset = Subscription.objects.all()
    permission_classes = [IsAuthenticated, HasCustomerPermissions]
    lookup_field = "remote_subscription_id"

    def get_queryset(self):
        return Subscription.objects.all()

    def create(self, request):
        serializer = self.get_serializer(data=request.data, context={"request": request})
        if serializer.is_valid():
            result = serializer.save()
            return Response(result, status=201)
        logger.error(f"Validation errors: {serializer.errors}")
        return Response(serializer.errors, status=400)

    def retrieve(self, request, remote_subscription_id=None):
        subscription = StripeService().retrieve_subscription(remote_subscription_id)
        if not subscription:
            return Response({"error": "Subscription not found"}, status=404)
        return Response(subscription, status=200)

    def delete(self, request):
        remote_subscription_id = request.query_params.get("remote_subscription_id")
        customer = get_customer(False, request.user)
        if not customer:
            return Response({"error": "Customer not found"}, status=404)
        try:
            subscription = Subscription.objects.filter(
                remote_subscription_id=remote_subscription_id,
                remote_customer_id=customer.remote_customer_id,
            )
            if not subscription.exists():
                return Response({"error": "Subscription not found"}, status=404)
            StripeService().delete_subscription(remote_subscription_id)
            subscription.delete()
            return Response({"status": "success"}, status=200)
        except NotFound:
            return Response({"error": "Subscription not found"}, status=404)
        except Exception as e:
            logger.exception(e)
            return Response({"error": "Error deleting subscription"}, status=500)

    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = StripeSubscriptionPatchSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        serializer.update(instance, serializer.validated_data)
        return Response(
            {"status": "success", "message": "Subscription updated in Stripe"}, status=200
        )


class StripeWebhookViewset(viewsets.GenericViewSet):
    serializer_class = StripeWebhookSerializer
    permission_classes = []

    def create(self, request):
        endpoint_secret = settings.STRIPE_WEBHOOK_SECRET
        response = StripeWebhookHandler().webhook_handler(request, endpoint_secret)
        return response


class StripeProductViewset(viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = StripeProductSerializer
    lookup_field = "remote_product_id"

    def list(self, request):
        products = StripeService().list_products()
        return Response(products, status=200)

    def retrieve(self, request, remote_product_id=None):
        product = StripeService().retrieve_product(remote_product_id)
        if not product:
            return Response({"error": "Product not found"}, status=404)
        serializer = self.serializer_class(product)
        return Response(serializer.data, status=200)


class StripeCustomerViewset(viewsets.GenericViewSet):
    serializer_class = StripeCustomerSerializer
    queryset = Customer.objects.all()
    permission_classes = [IsAuthenticated]

    def create(self, request):
        serializer = self.get_serializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=201)

    def retrieve(self, request, pk=None):
        remote_customer_id = request.query_params.get("customer_id")
        if pk == "me":
            customer = get_customer(False, request.user)
        else:
            if not remote_customer_id:
                return Response({"error": "Missing customer_id"}, status=400)
            customer = get_customer(remote_customer_id, request.user)
        if not customer:
            return Response({"error": "Customer not found"}, status=404)
        serializer = self.get_serializer(customer)
        return Response(serializer.data, status=200)


class StripePaymentMethodViewset(viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated, HasCustomerPermissions]
    serializer_class = StripePaymentMethodSerializer

    def list(self, request):
        try:
            stripe_service = StripeService()
            remote_customer_id = request.query_params.get("customer_id")
            if not remote_customer_id:
                return Response({"error": "Missing customer_id"}, status=400)
            customer = get_customer(remote_customer_id, request.user, stripe_service)
            if not customer:
                return Response({"error": "Customer not found"}, status=404)
            payment_methods = stripe_service.get_customer_payment_methods(remote_customer_id)
            serializer = self.get_serializer(payment_methods, many=True)
            return Response(serializer.data, status=200)
        except Exception as e:
            logger.exception("Failed to retrieve payment methods: %s", e)
            return Response({"error": "An internal error has occurred"}, status=500)

    # This method is used to create a new creating SetupIntent in Stripe
    def create(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            remote_customer_id = request.query_params.get("customer_id")
            if not remote_customer_id:
                return Response({"error": "Missing customer_id"}, status=400)
            customer = get_customer(remote_customer_id, request.user)
            if not customer:
                return Response({"error": "Customer not found"}, status=404)
            result = serializer.create(serializer.validated_data)
            return Response(result, status=201)
        except ValidationError:
            return Response({"error": "Invalid input provided"}, status=400)
        except Exception as e:
            logger.exception("Failed to create payment method: %s", e)
            return Response({"error": "An internal error has occurred"}, status=500)

    def update(self, request, pk=None):
        serializer = self.get_serializer(data={"pk": pk, **request.data})
        serializer.is_valid(raise_exception=True)
        try:
            remote_customer_id = request.query_params.get("customer_id")
            if not remote_customer_id:
                return Response({"error": "Missing customer_id"}, status=400)
            customer = get_customer(remote_customer_id, request.user, None, create_customer=False)
            if not customer:
                return Response({"error": "Customer not found"}, status=404)
            result = serializer.update(serializer.validated_data)
            return Response(result, status=200)
        except Exception as e:
            logger.exception("Failed to update payment method: %s", e)
            return Response({"error": "An internal error has occurred"}, status=500)

    def delete(self, request, pk=None):
        try:
            stripe_service = StripeService()
            remote_customer_id = request.query_params.get("customer_id")
            if not remote_customer_id:
                return Response({"error": "Missing customer_id"}, status=400)
            customer = get_customer(remote_customer_id, request.user, stripe_service)
            if not customer:
                return Response({"error": "Customer not found"}, status=404)
            stripe_service.delete_payment_method(
                pk, remote_customer_id, request.query_params.get("is_default")
            )
            return Response({}, status=204)
        except Exception as e:
            logger.exception("Failed to delete payment method: %s", e)
            return Response({"error": "An internal error has occurred"}, status=500)


class StripeInvoiceViewset(viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated, HasCustomerPermissions]
    serializer_class = StripeInvoiceSerializer

    # This is necessary to avoid errors when using the list method without a table in our db,
    # using only Stripe's API.
    def get_queryset(self):
        return []

    def list(self, request):
        remote_customer_id = request.query_params.get("customer_id")
        customer = get_customer(remote_customer_id, request.user)
        if not customer:
            return Response({"error": "Customer not found"}, status=404)
        try:
            invoices = StripeService().get_user_invoices(customer.remote_customer_id)
            serializer = self.get_serializer(invoices, many=True)
            page = self.paginate_queryset(serializer.data)
            if page is not None:
                return self.get_paginated_response(page)
            return Response(serializer.data, status=200)
        except Exception as e:
            logger.exception("Failed to retrieve invoices: %s", e)
            return Response({"error": "An internal error has occurred"}, status=500)
