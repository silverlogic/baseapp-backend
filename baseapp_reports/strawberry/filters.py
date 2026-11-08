import django_filters
import swapper
from django.db.models import QuerySet

from baseapp_core.graphql import get_pk_from_relay_id

Report = swapper.load_model("baseapp_reports", "Report")


class ReportFilter(django_filters.FilterSet):
    """Graphene's `filter_fields = {"id": ["exact"]}`: `id` takes a relay id."""

    id = django_filters.CharFilter(method="filter_id")

    class Meta:
        model = Report
        fields = ["id"]

    def filter_id(self, queryset: QuerySet, name: str, value: str) -> QuerySet:
        return queryset.filter(pk=get_pk_from_relay_id(value))
