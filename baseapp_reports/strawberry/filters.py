import django_filters
import swapper
from django.db.models import Q, QuerySet

from baseapp_core.graphql import get_pk_from_relay_id

Report = swapper.load_model("baseapp_reports", "Report")
ReportType = swapper.load_model("baseapp_reports", "ReportType")


class ReportFilter(django_filters.FilterSet):
    """`id` takes a relay id."""

    id = django_filters.CharFilter(method="filter_id")

    class Meta:
        model = Report
        fields = ["id"]

    def filter_id(self, queryset: QuerySet, name: str, value: str) -> QuerySet:
        return queryset.filter(pk=get_pk_from_relay_id(value))


class ReportTypeFilter(django_filters.FilterSet):
    top_level_only = django_filters.BooleanFilter(method="filter_top_level_only")
    target_object_id = django_filters.CharFilter(method="filter_target_object_id")

    def filter_top_level_only(self, queryset: QuerySet, name: str, value: bool) -> QuerySet:
        if value:
            return queryset.filter(Q(parent_type__isnull=True))
        return queryset

    def filter_target_object_id(self, queryset: QuerySet, name: str, value: str) -> QuerySet:
        return queryset

    class Meta:
        model = ReportType
        fields = ["top_level_only", "target_object_id"]
