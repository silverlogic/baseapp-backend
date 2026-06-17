import django_filters
from django.apps import apps
from django.core.exceptions import ValidationError
from django.db.models import Q

from baseapp_core.plugins import apply_if_installed

from ..models import ActivityLog


class ActivityLogFilter(django_filters.FilterSet):
    created_from = django_filters.DateFilter(field_name="created_at", lookup_expr="date__gte")
    created_to = django_filters.DateFilter(field_name="created_at", lookup_expr="date__lte")
    user_pk = django_filters.NumberFilter(field_name="user_id")
    user_name = django_filters.CharFilter(method="filter_user_name")

    if apps.is_installed("baseapp_profiles"):
        profile_pk = django_filters.NumberFilter(field_name="profile_id")

    def filter_user_name(self, queryset, name, value):
        if apps.is_installed("baseapp_profiles"):
            return queryset.filter(
                Q(user__profile__name__icontains=value) | Q(user__email__icontains=value)
            )
        return queryset.filter(user__email__icontains=value)

    def filter_queryset(self, queryset):
        created_from = self.data.get("created_from")
        created_to = self.data.get("created_to")

        if created_from and created_to and created_from > created_to:
            raise ValidationError("`created_from` must be earlier than or equal to `created_to`.")
        return super().filter_queryset(queryset)

    class Meta:
        model = ActivityLog
        fields = [
            "created_from",
            "created_to",
            "user_pk",
            *apply_if_installed("baseapp_profiles", ["profile_pk"]),
            "user_name",
        ]


class MiddlewareEventFilter(django_filters.FilterSet):
    created_from = django_filters.DateFilter(field_name="pgh_created_at__gte")
    created_to = django_filters.DateFilter(field_name="pgh_created_at__lte")
    user_pk = django_filters.NumberFilter(field_name="user_id")

    class Meta:
        model = ActivityLog
        fields = ["created_from", "created_to", "user_pk"]
