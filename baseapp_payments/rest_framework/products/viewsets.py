from drf_spectacular.utils import (
    OpenApiParameter,
    OpenApiTypes,
    extend_schema,
    extend_schema_view,
)
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from baseapp_payments.utils import StripeService

from .serializers import StripeProductSerializer


@extend_schema_view(
    retrieve=extend_schema(
        parameters=[
            OpenApiParameter(
                "remote_product_id",
                OpenApiTypes.STR,
                location=OpenApiParameter.PATH,
            )
        ]
    )
)
class StripeProductViewSet(viewsets.GenericViewSet):
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
