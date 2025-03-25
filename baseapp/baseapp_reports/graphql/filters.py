import django_filters
from django.db.models import Q

from ..models import ReportType

from baseapp_core.graphql import get_pk_from_relay_id


class ReportTypeFilter(django_filters.FilterSet):
    top_level_only = django_filters.BooleanFilter(method="filter_top_level_only")
    target_object_id = django_filters.CharFilter(method='filter_target_object_id')

    def filter_top_level_only(self, queryset, name, value):
        if value:
            return queryset.filter(Q(parent_type__isnull=True))
        return queryset

    def filter_target_object_id(self, queryset, name, value):
        print("========================XABLOU=========================")
        target_object_id = self.data.get("target_object_id")
        if not target_object_id:
            return queryset
        pk = get_pk_from_relay_id(target_object_id)
        print(pk)
        return queryset

        # return queryset.filter(content_types__pk=content_type.pk)

    class Meta:
        model = ReportType
        fields = ["top_level_only", "target_object_id"]
