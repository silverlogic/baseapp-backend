"""FilterSet filters taking Relay ids (any hashids strategy), exposed as `ID` arguments."""

from typing import Any

import django_filters
from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _


def _pk(value: str) -> Any:
    from baseapp_core.graphql.utils import get_pk_from_relay_id

    try:
        pk = get_pk_from_relay_id(value)
    except Exception as error:
        raise ValidationError(_("Invalid ID: %(value)s"), params={"value": value}) from error
    if pk is None:
        raise ValidationError(_("Invalid ID: %(value)s"), params={"value": value})
    return pk


class GlobalIDFormField(forms.CharField):
    def to_python(self, value: Any) -> Any:
        value = super().to_python(value)
        return _pk(value) if value else None


class GlobalIDMultipleChoiceField(forms.MultipleChoiceField):
    def valid_value(self, value: Any) -> bool:
        return True

    def to_python(self, value: Any) -> list[Any]:
        return [_pk(v) for v in super().to_python(value) if v]


class GlobalIDFilter(django_filters.Filter):
    field_class = GlobalIDFormField


class GlobalIDMultipleChoiceFilter(django_filters.MultipleChoiceFilter):
    field_class = GlobalIDMultipleChoiceField
