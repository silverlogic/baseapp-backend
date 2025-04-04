import django_filters
import swapper
from django.db.models import Q

Comment = swapper.load_model("baseapp_comments", "Comment")


class CommentFilter(django_filters.FilterSet):
    q = django_filters.CharFilter(method="filter_q")

    order_by = django_filters.OrderingFilter(
        fields=(
            ("created", "created"),
            ("is_pinned", "is_pinned"),
            ("reactions_count__total", "reactions_count_total"),
            ("comments_count__total", "replies_count_total"),
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
