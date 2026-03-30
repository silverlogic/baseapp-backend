import logging

import swapper
from rest_framework import viewsets
from rest_framework.exceptions import NotFound
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from baseapp_payments.utils import StripeService

from .serializers import StripeSubscriptionPatchSerializer, StripeSubscriptionSerializer

logger = logging.getLogger(__name__)

Customer = swapper.load_model("baseapp_payments", "Customer")
Subscription = swapper.load_model("baseapp_payments", "Subscription")


class StripeSubscriptionViewSet(
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
