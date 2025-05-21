import logging

import swapper
from constance import config
from django.apps import apps
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from rest_framework import viewsets
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Subscription
from .serializers import (
    StripeCustomerSerializer,
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
    permission_classes = [IsAuthenticated]
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
        customer = Customer.objects.filter(entity_id=self.request.user.id).first()
        if not customer:
            return Response({"error": "Customer does not exist."}, status=404)
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
        if pk == "me":
            customer_entity_model = config.STRIPE_CUSTOMER_ENTITY_MODEL
            entity_model = apps.get_model(customer_entity_model)
            model_content_type = ContentType.objects.get_for_model(entity_model)
            if customer_entity_model == "profiles.Profile":
                customer = Customer.objects.filter(
                    entity_id=request.user.profile.id, entity_type=model_content_type
                ).first()
            else:
                customer = Customer.objects.filter(
                    entity_id=request.user.id, entity_type=model_content_type
                ).first()
            if not customer:
                try:
                    customer = StripeService().retrieve_customer(email=request.user.email)
                    if customer:
                        Customer.objects.create(
                            entity=request.user.profile, remote_customer_id=customer.get("id")
                        )
                except Exception as e:
                    logger.exception("Failed to retrieve or create customer: %s", e)
                    return Response({"error": "An internal error has occurred"}, status=500)
        else:
            customer = Customer.objects.filter(remote_customer_id=pk).first()
        if not customer:
            return Response({"error": "Customer not found"}, status=404)
        serializer = self.get_serializer(customer)
        return Response(serializer.data, status=200)


class StripePaymentMethodViewset(viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = StripePaymentMethodSerializer

    def list(self, request):
        remote_customer_id = request.query_params.get("customer_id")
        stripe_service = StripeService()
        if not remote_customer_id:
            return Response({"error": "Missing customer_id"}, status=400)
        if not stripe_service.checkCustomerIdForUser(remote_customer_id, request.user):
            return Response(
                {"error": "The provided customer_id does not belong to the authenticated user."},
                status=401,
            )
        try:
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
            remote_customer_id = request.data.get("customer_id")
            if not remote_customer_id:
                return Response({"error": "Missing customer_id"}, status=400)
            if not StripeService().checkCustomerIdForUser(remote_customer_id, request.user):
                return Response(
                    {
                        "error": "The provided customer_id does not belong to the authenticated user."
                    },
                    status=401,
                )
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
            remote_customer_id = request.data.get("customer_id")
            if not remote_customer_id:
                return Response({"error": "Missing customer_id"}, status=400)
            if not StripeService().checkCustomerIdForUser(remote_customer_id, request.user):
                return Response(
                    {
                        "error": "The provided customer_id does not belong to the authenticated user."
                    },
                    status=401,
                )
            result = serializer.update(serializer.validated_data)
            return Response(result, status=200)
        except Exception as e:
            logger.exception("Failed to update payment method: %s", e)
            return Response({"error": "An internal error has occurred"}, status=500)

    def delete(self, request, pk=None):
        try:
            remote_customer_id = request.query_params.get("customer_id")
            stripe_service = StripeService()
            if not remote_customer_id:
                return Response({"error": "Missing customer_id"}, status=400)
            if not stripe_service.checkCustomerIdForUser(remote_customer_id, request.user):
                return Response(
                    {
                        "error": "The provided customer_id does not belong to the authenticated user."
                    },
                    status=401,
                )
            stripe_service.delete_payment_method(
                pk, remote_customer_id, request.query_params.get("is_default")
            )
            return Response({}, status=204)
        except Exception as e:
            logger.exception("Failed to delete payment method: %s", e)
            return Response({"error": "An internal error has occurred"}, status=500)
