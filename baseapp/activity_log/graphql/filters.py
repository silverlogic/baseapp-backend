import django_filters
from django.core.exceptions import ValidationError
from django.db.models import Q

from ..models import ActivityLog


class ActivityLogFilter(django_filters.FilterSet):
    created_from = django_filters.DateFilter(field_name="created_at", lookup_expr="date__gte")
    created_to = django_filters.DateFilter(field_name="created_at", lookup_expr="date__lte")
    user_pk = django_filters.NumberFilter(field_name="user_id")
    profile_pk = django_filters.NumberFilter(field_name="profile_id")
    user_name = django_filters.CharFilter(method="filter_user_name")

    def filter_user_name(self, queryset, name, value):
        return queryset.filter(
            Q(user__profile__name__icontains=value) | Q(user__email__icontains=value)
        )

    def filter_queryset(self, queryset):
        created_from = self.data.get("created_from")
        created_to = self.data.get("created_to")

        if created_from and created_to and created_from > created_to:
            raise ValidationError("`created_from` must be earlier than or equal to `created_to`.")
        return super().filter_queryset(queryset)

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
