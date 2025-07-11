import logging

import swapper
from django.conf import settings
from rest_framework import viewsets
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from baseapp_core.rest_framework.decorators import action

from .models import Subscription
from .permissions import DRFCustomerPermissions, DRFSubscriptionPermissions
from .serializers import (
    StripeCustomerSerializer,
    StripeInvoiceSerializer,
    StripePaymentMethodSerializer,
    StripeProductSerializer,
    StripeSubscriptionPatchSerializer,
    StripeSubscriptionSerializer,
    StripeWebhookSerializer,
)
from .utils import StripeService, StripeWebhookHandler

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
    permission_classes = [IsAuthenticated, DRFSubscriptionPermissions]
    lookup_field = "remote_subscription_id"

    def create(self, request):
        serializer = self.get_serializer(data=request.data, context={"request": request})
        if serializer.is_valid():
            result = serializer.save()
            return Response(result, status=201)
        logger.error(f"Validation errors: {serializer.errors}")
        return Response(serializer.errors, status=400)

    def delete(self, request, *args, **kwargs):
        try:
            subscription = self.get_object()
            StripeService().delete_subscription(subscription.remote_subscription_id)
            subscription.delete()
            return Response({}, status=204)
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

    def list(self, request):
        products = StripeService().list_products()
        return Response(products, status=200)

    def retrieve(self, request, productId=None):
        product = StripeService().retrieve_product(productId)
        if not product:
            return Response({"error": "Product not found"}, status=404)
        serializer = self.serializer_class(product)
        return Response(serializer.data, status=200)


class StripeCustomerViewset(viewsets.GenericViewSet, viewsets.mixins.RetrieveModelMixin):
    serializer_class = StripeCustomerSerializer
    queryset = Customer.objects.all()
    permission_classes = [IsAuthenticated, DRFCustomerPermissions]
    lookup_field = "entity_id"

    def create(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=201)

    @action(
        methods=["GET"],
        detail=True,
        serializer_class=StripeInvoiceSerializer,
    )
    def invoices(self, request, pk=None, *args, **kwargs):
        customer = self.get_object()
        invoices = StripeService().get_customer_invoices(customer.remote_customer_id)
        serializer = self.get_serializer(invoices.data, many=True)
        return Response(data=serializer.data, status=200)

    @action(
        methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        detail=True,
        serializer_class=StripePaymentMethodSerializer,
        url_path="payment_methods(?:/(?P<payment_method_id>[^/.]+))?",
    )
    def payment_methods(self, request, pk=None, payment_method_id=None, *args, **kwargs):
        customer = self.get_object()
        request.query_params = request.query_params.copy()
        request.query_params["customer"] = customer
        payment_method_viewset = StripePaymentMethodViewset()
        payment_method_viewset.request = request
        payment_method_viewset.format_kwarg = getattr(self, "format_kwarg", None)
        if request.method == "GET":
            return payment_method_viewset.list(request)
        elif request.method == "POST":
            return payment_method_viewset.create(request)
        elif request.method in ["PUT", "PATCH"]:
            if not payment_method_id:
                return Response(
                    {"error": "payment_method_id is required in URL path for update operations"},
                    status=400,
                )
            return payment_method_viewset.update(request, pk=payment_method_id)
        elif request.method == "DELETE":
            if not payment_method_id:
                return Response(
                    {"error": "payment_method_id is required in URL path for delete operations"},
                    status=400,
                )
            return payment_method_viewset.delete(request, pk=payment_method_id)


class StripePaymentMethodViewset(viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated, DRFCustomerPermissions]
    serializer_class = StripePaymentMethodSerializer

    def list(self, request):
        try:
            customer = request.query_params.get("customer")
            payment_methods = StripeService().get_customer_payment_methods(
                customer.remote_customer_id
            )
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
            result = serializer.update(serializer.validated_data)
            return Response(result, status=200)
        except Exception as e:
            logger.exception("Failed to update payment method: %s", e)
            return Response({"error": "An internal error has occurred"}, status=500)

    def delete(self, request, pk=None):
        try:
            customer = request.query_params.get("customer")
            StripeService().delete_payment_method(
                pk, customer.remote_customer_id, request.query_params.get("is_default")
            )
            return Response({}, status=204)
        except Exception as e:
            logger.exception("Failed to delete payment method: %s", e)
            return Response({"error": "An internal error has occurred"}, status=500)
