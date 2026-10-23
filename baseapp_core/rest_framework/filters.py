import uuid
from typing import Any

import django_filters
from django import forms
from django.db import models
from django.utils.translation import gettext_lazy as _
from django_filters.widgets import QueryArrayWidget

from baseapp_core.hashids.strategies import (
    drf_get_pk_from_public_id_or_pk,
    drf_get_pk_from_public_id_using_strategy,
    should_use_public_id,
)
from baseapp_core.hashids.strategies.interfaces import DRFResolverStrategy
from baseapp_core.hashids.utils import is_uuid4


class _NoMatch:
    """Cleaned value of a public id that maps to no row: the filter matches nothing."""

    def __repr__(self) -> str:
        return "NO_MATCH"


NO_MATCH = _NoMatch()


class PublicIdFormField(forms.Field):
    """Form field that cleans a public id (or, while allowed, an integer pk) of `model` to its pk.

    An id of another model, or a pk while pk lookups are disallowed, is a validation error. A
    public id that maps to no row cleans to `NO_MATCH`, so the filter answers an empty list just
    as it does for a row outside the queryset, and does not tell whether that id exists.
    """

    default_error_messages = {
        "invalid": _("Select a valid id. That id is not one of the available choices."),
    }

    def __init__(
        self, *, model: type[models.Model], allow_pk_lookup: bool | None = None, **kwargs: Any
    ) -> None:
        self.model = model
        self.allow_pk_lookup = allow_pk_lookup
        super().__init__(**kwargs)

    def resolve(self, value: Any) -> Any:
        if is_uuid4(value) and should_use_public_id(self.model):
            try:
                pk = drf_get_pk_from_public_id_using_strategy(value, expected_model=self.model)
            except DRFResolverStrategy.NoInstanceFound:
                raise forms.ValidationError(self.error_messages["invalid"], code="invalid")
            return NO_MATCH if pk is None else pk
        pk = drf_get_pk_from_public_id_or_pk(
            value, self.model, allow_pk_lookup=self.allow_pk_lookup
        )
        if pk is None:
            raise forms.ValidationError(self.error_messages["invalid"], code="invalid")
        return pk

    def to_python(self, value: Any) -> Any:
        if value in self.empty_values:
            return None
        if isinstance(value, uuid.UUID):
            value = str(value)
        return self.resolve(str(value).strip())


class PublicIdMultipleFormField(PublicIdFormField):
    """`PublicIdFormField` for several ids: `?f=<id>&f=<id>` or `?f=<id>,<id>`."""

    widget = QueryArrayWidget

    def to_python(self, value: Any) -> list[Any]:
        if value in self.empty_values:
            return []
        if isinstance(value, (str, uuid.UUID)):
            value = [value]
        ids = [part.strip() for item in value for part in str(item).split(",")]
        return [self.resolve(public_id) for public_id in dict.fromkeys(ids) if public_id]


class _PublicIdFilterMixin:
    def __init__(self, *args: Any, model: type[models.Model] | None = None, **kwargs: Any) -> None:
        self.target_model = model
        super().__init__(*args, **kwargs)

    def get_target_model(self) -> type[models.Model]:
        """The model whose ids the filter takes: `model=` if given, else the model `field_name`
        points at on the FilterSet's model (the related model for a relation, the model itself
        for its pk)."""
        if self.target_model is not None:
            return self.target_model
        current = self.model
        for name in self.field_name.split("__"):
            field = current._meta.get_field(name)
            if field.is_relation:
                current = field.related_model
        return current

    @property
    def field(self) -> forms.Field:
        if not hasattr(self, "_field"):
            self.extra["model"] = self.get_target_model()
        return super().field

    def filter_no_match(self, qs: models.QuerySet) -> models.QuerySet:
        """The result when every id given maps to no row."""
        return qs if self.exclude else qs.none()


class PublicIdFilter(_PublicIdFilterMixin, django_filters.Filter):
    """Filter by the public id of a related object (or of the row itself).

    `PublicIdFilter(field_name="author")` takes `?author=<public id>` and filters on the author's
    pk. The model is inferred from `field_name` on the FilterSet's model, or given with `model=`.
    An id of another model gives a 400, and an unknown public id matches nothing. Integer pks
    are accepted while `allow_pk_lookup` is true (default: `BASEAPP_PUBLIC_ID_ALLOW_PK_LOOKUP`),
    and always for models without public ids.
    """

    field_class = PublicIdFormField

    def filter(self, qs: models.QuerySet, value: Any) -> models.QuerySet:
        if value is NO_MATCH:
            return self.filter_no_match(qs)
        return super().filter(qs, value)


class PublicIdMultipleFilter(_PublicIdFilterMixin, django_filters.Filter):
    """`PublicIdFilter` for several ids, matching any of them (`__in`).

    Takes `?author=<id>&author=<id>` or `?author=<id>,<id>`.
    """

    field_class = PublicIdMultipleFormField

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        kwargs.setdefault("lookup_expr", "in")
        super().__init__(*args, **kwargs)

    def filter(self, qs: models.QuerySet, value: Any) -> models.QuerySet:
        if value and any(pk is NO_MATCH for pk in value):
            value = [pk for pk in value if pk is not NO_MATCH]
            if not value:
                return self.filter_no_match(qs)
        return super().filter(qs, value)
