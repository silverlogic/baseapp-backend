import logging

import swapper
from djstripe.models import Customer
from rest_framework import permissions, status, viewsets
from rest_framework.response import Response

from baseapp_core.decorators import action

from .serializers import (
    CancelSubscriptionSerializer,
    CapturePaymentEditSerializer,
    CapturePaymentIntentSerializer,
    CreatePaymentIntentSerializer,
    CustomerSerializer,
    EditPaymentMethodSerializer,
    SubscribeCustomerSerializer,
    UpdatingSubscriptionSerializer,
    get_serializer,
)
from .utils import (
    create_payment_intent,
    delete_payment_method,
    edit_payment_method,
    get_customer_payment_methods,
    make_another_default_payment_method,
)

Plan = swapper.load_model("baseapp_payments", "Plan")


class StripePaymentsViewSet(
    viewsets.GenericViewSet,
):
    def get_queryset(self):
        # TO DO: remove method
        # this is just to trick the DRF web interface
        return Customer.objects.none()

    @action(detail=False, methods=["GET"])
    def plans(self, request):
        plans = Plan.objects.filter(is_active=True)
        PlanSerializer = get_serializer("PlanSerializer")
        serializer = PlanSerializer(plans, many=True, context={"request": request})
        return Response(serializer.data)

    @action(detail=False, methods=["GET"], permission_classes=[permissions.IsAuthenticated])
    def get_customer_method(self, request):
        try:
            customer, created = Customer.get_or_create(
                request.user.get_subscriber_from_request(request)
            )
            return Response(
                CustomerSerializer(customer, context={"request": request}).data,
                status=status.HTTP_201_CREATED,
            )

        except Exception as e:
            logging.exception(e)
            error = {"error": "Error getting customer"}
            return Response(error, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=["POST"], permission_classes=[permissions.IsAuthenticated])
    def create_payment_method(self, request):
        serializer = CapturePaymentIntentSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)

        try:
            customer, created = Customer.get_or_create(
                request.user.get_subscriber_from_request(request)
            )
            payment_method_id = serializer.validated_data["payment_method_id"]
            customer.add_payment_method(payment_method_id)

            return Response(
                {"payment_method_id": payment_method_id},
                status=status.HTTP_201_CREATED,
            )

        except Exception as e:
            logging.exception(e)
            error = {"error": "Error creating payment method"}
            return Response(error, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=["POST"], permission_classes=[permissions.IsAuthenticated])
    def start_subscription(self, request):
        serializer = SubscribeCustomerSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)

        try:
            serializer.save()
            return Response({}, status=status.HTTP_201_CREATED)
        except Exception as e:
            logging.exception(e)
            error = {"error": "Error creating subscription"}
            return Response(error, status=status.HTTP_400_BAD_REQUEST)

    @action(
        detail=False,
        methods=["POST"],
        permission_classes=[permissions.IsAuthenticated],
        serializer_class=CancelSubscriptionSerializer,
    )
    def cancel_subscription(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(
            {"msg": "Subscription was successfully canceled."},
            status=status.HTTP_200_OK,
        )

    @action(
        detail=False,
        methods=["POST"],
        permission_classes=[permissions.IsAuthenticated],
        serializer_class=UpdatingSubscriptionSerializer,
    )
    def update_subscription(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = serializer.save()
        if result["is_upgrade"]:
            return Response(
                {"msg": f"Subscription was successfully updated to {serializer.plan.name}."},
                status=status.HTTP_200_OK,
            )
        return Response(
            {
                "msg": f"Subscription will be updated to {serializer.plan.name} in your next billing cycle."
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=["GET"], permission_classes=[permissions.IsAuthenticated])
    def get_customer_payment_methods(self, request):
        customer, created = Customer.get_or_create(
            request.user.get_subscriber_from_request(request)
        )
        return Response(
            get_customer_payment_methods(customer.id),
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=["PUT"], permission_classes=[permissions.IsAuthenticated])
    def edit_payment_method(self, request):
        serializer = EditPaymentMethodSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        try:
            payment_method_id = serializer.validated_data["payment_method_id"]
            edit_payment_method(payment_method_id, serializer.validated_data)
            return Response(
                {"id": payment_method_id},
                status=status.HTTP_201_CREATED,
            )

        except Exception as e:
            logging.exception(e)
            error = {"error": "Error editing payment method"}
            return Response(error, status=status.HTTP_400_BAD_REQUEST)

    @action(
        detail=False,
        methods=["DELETE"],
        permission_classes=[permissions.IsAuthenticated],
    )
    def delete_payment_method(self, request):
        serializer = CapturePaymentEditSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        try:
            customer, created = Customer.get_or_create(
                request.user.get_subscriber_from_request(request)
            )
            payment_method_id = serializer.validated_data["payment_method_id"]
            delete_payment_method(payment_method_id, customer.id)
            return Response(
                {"id": payment_method_id},
                status=status.HTTP_200_OK,
            )

        except Exception as e:
            logging.exception(e)
            error = {"error": "Error deleting payment method"}
            return Response(error, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=["POST"], permission_classes=[permissions.IsAuthenticated])
    def make_primary_payment_method(self, request):
        serializer = CapturePaymentEditSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        try:
            customer, created = Customer.get_or_create(
                request.user.get_subscriber_from_request(request)
            )
            payment_method_id = serializer.validated_data["payment_method_id"]
            make_another_default_payment_method(customer.id, payment_method_id)
            return Response(
                {"id": payment_method_id},
                status=status.HTTP_200_OK,
            )

        except Exception as e:
            logging.exception(e)
            error = {"error": "Error making payment method primary"}
            return Response(error, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=["POST"], permission_classes=[permissions.IsAuthenticated])
    def create_payment(self, request):
        serializer = CreatePaymentIntentSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        product = data["product"]

        try:
            response = create_payment_intent(product, request, data)
            return Response(
                {"id": response.id},
                status=status.HTTP_200_OK,
            )

        except Exception as e:
            logging.exception(e)
            error = {"error": "Error creating payment intent"}
            return Response(error, status=status.HTTP_400_BAD_REQUEST)
