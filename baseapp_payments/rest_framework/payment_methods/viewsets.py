import logging

from drf_spectacular.utils import (
    OpenApiParameter,
    OpenApiTypes,
    extend_schema,
    extend_schema_view,
)
from rest_framework import viewsets
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from baseapp_payments.utils import StripeService

from .serializers import StripePaymentMethodSerializer

logger = logging.getLogger(__name__)


@extend_schema_view(
    update=extend_schema(
        parameters=[
            OpenApiParameter("pk", OpenApiTypes.STR, location=OpenApiParameter.PATH),
            OpenApiParameter("id", OpenApiTypes.STR, location=OpenApiParameter.PATH),
        ]
    ),
)
class StripePaymentMethodViewSet(viewsets.GenericViewSet):
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
