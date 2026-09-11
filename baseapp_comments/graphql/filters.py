from typing import TYPE_CHECKING

import django_filters
import swapper
from django.db.models import Q

from baseapp_core.plugins import apply_if_installed

if TYPE_CHECKING:
    from django.db.models import QuerySet

Comment = swapper.load_model("baseapp_comments", "Comment")


class CommentFilter(django_filters.FilterSet):
    q = django_filters.CharFilter(method="filter_q")

    order_by = django_filters.OrderingFilter(
        fields=(
            ("created", "created"),
            ("is_pinned", "is_pinned"),
            # `reactions_count_total` is annotated in `BaseCommentObjectType.pre_optimization_hook`,
            # if `baseapp_reactions` is installed.
            *apply_if_installed(
                "baseapp_reactions",
                [("reactions_count_total", "reactions_count_total")],
            ),
            # `replies_count_total` is annotated in `BaseCommentObjectType.pre_optimization_hook`
            ("replies_count_total", "replies_count_total"),
        )
    )

    class Meta:
        model = Comment
        fields = ["q", "order_by"]

    def filter_q(self, queryset, name, value) -> "QuerySet":
        return queryset.filter(
            Q(body__icontains=value)
            | Q(user__first_name__icontains=value)
            | Q(user__last_name__icontains=value)
            | Q(user__email__icontains=value)
        )
