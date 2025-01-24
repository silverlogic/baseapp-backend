import django_filters
from django.db.models import Q

from ..models import ActivityLog


class ActivityLogFilter(django_filters.FilterSet):
    created_from = django_filters.DateFilter(field_name="created_at__gte")
    created_to = django_filters.DateFilter(field_name="created_at__lte")
    user_pk = django_filters.NumberFilter(field_name="user_id")
    profile_pk = django_filters.NumberFilter(field_name="profile_id")
    user_name = django_filters.CharFilter(method="filter_user_name")

    def filter_user_name(self, queryset, name, value):
        return queryset.filter(
            Q(user__profile__name__icontains=value) | Q(user__email__icontains=value)
        )

    class Meta:
        model = ActivityLog
        fields = ["created_from", "created_to", "user_pk", "profile_pk", "user_name"]


class MiddlewareEventFilter(django_filters.FilterSet):
    created_from = django_filters.DateFilter(field_name="pgh_created_at__gte")
    created_to = django_filters.DateFilter(field_name="pgh_created_at__lte")
    user_pk = django_filters.NumberFilter(field_name="user_id")

    class Meta:
        model = ActivityLog
        fields = ["created_from", "created_to", "user_pk"]
