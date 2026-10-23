from typing import TYPE_CHECKING

import django_filters
from django.db.models import Q

from ..models import EmailTemplate
from ..registry import email_templates, is_customized

if TYPE_CHECKING:
    from django.db.models import QuerySet


class EmailTemplateFilter(django_filters.FilterSet):
    group = django_filters.CharFilter(method="filter_group")
    q = django_filters.CharFilter(method="filter_q")
    is_editable = django_filters.BooleanFilter(method="filter_is_editable")
    is_customized = django_filters.BooleanFilter(method="filter_is_customized")

    class Meta:
        model = EmailTemplate
        fields: list[str] = []

    def filter_group(self, queryset, name, value) -> "QuerySet":
        names = [template.name for template in email_templates.list(group=value)]
        return queryset.filter(name__in=names)

    def filter_q(self, queryset, name, value) -> "QuerySet":
        """Match the name, or the registered label or group."""
        needle = value.strip().lower()
        if not needle:
            return queryset
        names = [
            template.name
            for template in email_templates.list()
            if needle in str(template.label).lower() or needle in template.group.lower()
        ]
        return queryset.filter(Q(name__icontains=needle) | Q(name__in=names))

    def filter_is_editable(self, queryset, name, value) -> "QuerySet":
        names = [template.name for template in email_templates.list() if template.editable]
        if value:
            return queryset.filter(name__in=names)
        return queryset.exclude(name__in=names)

    def filter_is_customized(self, queryset, name, value) -> "QuerySet":
        pks = [row.pk for row in queryset if is_customized(row)]
        if value:
            return queryset.filter(pk__in=pks)
        return queryset.exclude(pk__in=pks)
