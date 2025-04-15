import django_filters
from django.db.models import Q

from ..models import ReportType


class ReportTypeFilter(django_filters.FilterSet):
    top_level_only = django_filters.BooleanFilter(method="filter_top_level_only")
    target_object_id = django_filters.CharFilter(method="filter_target_object_id")

    def filter_top_level_only(self, queryset, name, value):
        if value:
            return queryset.filter(Q(parent_type__isnull=True))
        return queryset

    def filter_target_object_id(self, queryset, name, value):
        return queryset

    class Meta:
        model = ReportType
        fields = ["top_level_only", "target_object_id"]
