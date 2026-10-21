from typing import TYPE_CHECKING

import django_filters
import swapper
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from ..groups import get_notification_group

if TYPE_CHECKING:
    from django.db.models import QuerySet

Notification = swapper.load_model("notifications", "Notification")


class NotificationFilter(django_filters.FilterSet):
    verbs = django_filters.CharFilter(method="filter_by_verbs")
    group = django_filters.CharFilter(
        method="filter_by_group",
        help_text=_("Notifications whose verb is the group key or starts with `<group>.`."),
    )

    class Meta:
        model = Notification
        fields = ["level", "unread"]

    def filter_by_verbs(self, queryset, name, value) -> "QuerySet":
        verbs = value.split(",")
        return queryset.filter(verb__in=verbs)

    def filter_by_group(self, queryset: "QuerySet", name: str, value: str) -> "QuerySet":
        condition = Q(verb=value) | Q(verb__startswith=f"{value}.")
        # A registered group with an explicit verb list also owns verbs outside its prefix.
        group = get_notification_group(value)
        if group is not None and group.verbs:
            condition |= Q(verb__in=group.verbs)
        return queryset.filter(condition)
