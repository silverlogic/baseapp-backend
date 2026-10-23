from typing import TYPE_CHECKING, Any, Optional, Type

from django.core.exceptions import ImproperlyConfigured
from django.db.models import QuerySet
from django.db.models.query import ModelIterable
from django.http import Http404
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response

if TYPE_CHECKING:
    from django.db.models import Model

UUID4_LOOKUP_REGEX = (
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-4[0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}"
)
# Matches an integer pk or a public id (UUID4), so a router emits one detail pattern for both.
PUBLIC_ID_LOOKUP_REGEX = rf"[0-9]+|{UUID4_LOOKUP_REGEX}"


class PublicIdLookupMixin:
    """Mixin to resolve public_id (UUID) URL kwargs to numeric PKs.

    - A public id of another model, or one that maps to nothing, answers 404.
    - An integer pk is still accepted while `allow_pk_lookup` is true. It defaults to the setting
      `BASEAPP_PUBLIC_ID_ALLOW_PK_LOOKUP` (default True); when false, a pk lookup on a model that
      uses public ids answers 404.
    - The detail route only matches an integer or a UUID4 (`PUBLIC_ID_LOOKUP_REGEX`); set
      `lookup_value_regex` on the viewset to look up by anything else.
    - Querysets are annotated with `mapped_public_id`, so serializing a list does not query the
      DocumentId table once per row. Set `annotate_mapped_public_id = False` to skip it.
    """

    lookup_value_regex = PUBLIC_ID_LOOKUP_REGEX
    allow_pk_lookup: Optional[bool] = None
    annotate_mapped_public_id: bool = True

    def is_pk_lookup_allowed(self) -> bool:
        from baseapp_core.hashids.strategies import is_public_id_pk_lookup_allowed

        if self.allow_pk_lookup is not None:
            return self.allow_pk_lookup
        return is_public_id_pk_lookup_allowed()

    def filter_queryset(self, queryset: QuerySet) -> QuerySet:
        # Annotated here rather than in get_queryset() so it also applies when a viewset
        # overrides get_queryset() without calling super().
        queryset = super().filter_queryset(queryset)
        if (
            self.annotate_mapped_public_id
            and isinstance(queryset, QuerySet)
            and queryset._iterable_class is ModelIterable
            and not queryset.query.combinator
        ):
            from baseapp_core.hashids.strategies import annotate_public_ids

            queryset = annotate_public_ids(queryset)
        return queryset

    def get_object(self) -> "Model":
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
                should_use_public_id,
            )
            from baseapp_core.hashids.strategies.interfaces import DRFResolverStrategy

            try:
                resolved = drf_get_pk_from_public_id_using_strategy(
                    lookup_val, expected_model=expected_model
                )
            except DRFResolverStrategy.NoInstanceFound:
                raise Http404
            if resolved is None:
                raise Http404
            if isinstance(resolved, int):
                # apply same filtering/context the view would use
                queryset = self.filter_queryset(self.get_queryset())
                obj = get_object_or_404(queryset, pk=resolved)
                # preserve DRF permission checks
                self.check_object_permissions(self.request, obj)
                return obj

            if (
                expected_model is not None
                and getattr(self, "lookup_field", "pk") in ("pk", expected_model._meta.pk.name)
                and str(lookup_val).isdigit()
                and should_use_public_id(expected_model)
                and not self.is_pk_lookup_allowed()
            ):
                raise Http404
        return super().get_object()


class DestroyModelMixin:
    """Destroy mixin that returns empty object as response.

    iOS requires that every response contains a JSON serializable
    object because of the framework they use.

    """

    def destroy(self, request: Request, *args: Any, **kwargs: Any) -> Response:  # NOSONAR
        instance = self.get_object()
        self.perform_destroy(instance)
        return Response({}, status=status.HTTP_204_NO_CONTENT)

    def perform_destroy(self, instance) -> None:
        instance.delete()
