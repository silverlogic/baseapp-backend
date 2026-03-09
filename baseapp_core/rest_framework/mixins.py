from typing import Optional, Type

from django.core.exceptions import ImproperlyConfigured
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response


class PublicIdLookupMixin:
    """Mixin to resolve public_id (UUID) URL kwargs to numeric PKs."""

    def get_object(self):
        """Attempt to resolve a public_id in the lookup kwarg and fetch the
        corresponding object without mutating self.kwargs.
        This applies the view's queryset filters and permission checks to
        preserve DRF semantics.
        """
        lookup_url_kwarg = getattr(self, "lookup_url_kwarg", None) or getattr(
            self, "lookup_field", "pk"
        )
        if lookup_url_kwarg and lookup_url_kwarg in self.kwargs:
            lookup_val = self.kwargs[lookup_url_kwarg]
            expected_model: Optional[Type] = None
            try:
                expected_model = self.get_queryset().model
            except (ImproperlyConfigured, AttributeError):
                expected_model = None

            from baseapp_core.hashids.strategies import (
                drf_get_pk_from_public_id_using_strategy,
            )

            resolved = drf_get_pk_from_public_id_using_strategy(
                lookup_val, expected_model=expected_model
            )
            if isinstance(resolved, int):
                # apply same filtering/context the view would use
                queryset = self.filter_queryset(self.get_queryset())
                obj = get_object_or_404(queryset, pk=resolved)
                # preserve DRF permission checks
                self.check_object_permissions(self.request, obj)
                return obj
        return super().get_object()


class DestroyModelMixin:
    """Destroy mixin that returns empty object as response.

    iOS requires that every response contains a JSON serializable
    object because of the framework they use.

    """

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)
        return Response({}, status=status.HTTP_204_NO_CONTENT)

    def perform_destroy(self, instance):
        instance.delete()
