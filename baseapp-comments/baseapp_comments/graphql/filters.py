import django_filters
from django.db.models import Q

from ..models import Comment


class CommentFilter(django_filters.FilterSet):
    q = django_filters.CharFilter(method="filter_q")

    order_by = django_filters.OrderingFilter(
        fields=(
            ("created", "created"),
            ("is_pinned", "is_pinned"),
        )
    )

    class Meta:
        model = Comment
        fields = ["q", "order_by"]

    def filter_q(self, queryset, name, value):
        return queryset.filter(
            Q(body__icontains=value)
            | Q(user__first_name__icontains=value)
            | Q(user__last_name__icontains=value)
            | Q(user__email__icontains=value)
        )
