from typing import Any, Optional, Type

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
        lookup_url_kwarg = self.lookup_url_kwarg or self.lookup_field
        if lookup_url_kwarg and lookup_url_kwarg in self.kwargs:
            lookup_val = self.kwargs[lookup_url_kwarg]
            # infer expected model from the view's queryset if possible
            expected_model: Optional[Type] = None
            try:
                expected_model = self.get_queryset().model
            except Exception:
                expected_model = None

            resolved = self.resolve_public_id_to_pk(lookup_val, expected_model=expected_model)
            if isinstance(resolved, int):
                # apply same filtering/context the view would use
                queryset = self.filter_queryset(self.get_queryset())
                obj = get_object_or_404(queryset, pk=resolved)
                # preserve DRF permission checks
                self.check_object_permissions(self.request, obj)
                return obj
        return super().get_object()

    @staticmethod
    def resolve_public_id_to_pk(value: Any, expected_model: Optional[Type] = None):
        """Try to resolve `value` (possibly a public_id) into an integer PK.
        expected_model: optional model class to validate mapping belongs to it.
        """
        try:
            # allow ints or numeric strings
            if isinstance(value, int):
                return value
            if isinstance(value, str) and value.isdigit():
                return int(value)
        except Exception:
            pass
        # Lazy import to avoid circular imports
        try:
            from baseapp_core.hashids.models import PublicIdMapping
        except Exception:
            return value

        try:
            content_type, object_id = PublicIdMapping.get_content_type_and_id(value)
            if not (content_type and object_id):
                return value
            model_cls = content_type.model_class()
            if expected_model is not None:
                try:
                    expected_cls = (
                        expected_model.model if hasattr(expected_model, "model") else expected_model
                    )
                except Exception:
                    expected_cls = expected_model
                if model_cls != expected_cls:
                    return value
            return object_id
        except Exception:
            return value


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
