from typing import TYPE_CHECKING

import django_filters
import swapper

if TYPE_CHECKING:
    from django.db.models import QuerySet

Notification = swapper.load_model("notifications", "Notification")


class NotificationFilter(django_filters.FilterSet):
    verbs = django_filters.CharFilter(method="filter_by_verbs")

    class Meta:
        model = Notification
        fields = ["level", "unread"]

    def filter_by_verbs(self, queryset, name, value) -> "QuerySet":
        verbs = value.split(",")
        return queryset.filter(verb__in=verbs)
