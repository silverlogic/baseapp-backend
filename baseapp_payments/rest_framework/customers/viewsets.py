import logging

import swapper
from constance import config
from django.apps import apps
from django.contrib.contenttypes.models import ContentType
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from baseapp_payments.utils import StripeService

from .serializers import StripeCustomerSerializer

logger = logging.getLogger(__name__)

Customer = swapper.load_model("baseapp_payments", "Customer")


class StripeCustomerViewSet(viewsets.GenericViewSet):
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
