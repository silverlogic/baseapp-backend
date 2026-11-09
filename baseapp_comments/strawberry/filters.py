import django_filters
import swapper
from django.db.models import Q, QuerySet

from baseapp_core.plugins import apply_if_installed, shared_services

Comment = swapper.load_model("baseapp_comments", "Comment")

# Ordering aliases and the metadata service that annotates each one.
_ORDERING_ANNOTATIONS = {
    "replies_count_total": "commentable_metadata",
    "reactions_count_total": "reactable_metadata",
}


class CommentFilter(django_filters.FilterSet):
    """Annotates an ordering alias only when the queryset is ordered by it."""

    q = django_filters.CharFilter(method="filter_q")

    order_by = django_filters.OrderingFilter(
        fields=(
            ("created", "created"),
            ("is_pinned", "is_pinned"),
            *apply_if_installed(
                "baseapp_reactions",
                [("reactions_count_total", "reactions_count_total")],
            ),
            ("replies_count_total", "replies_count_total"),
        )
    )

    class Meta:
        model = Comment
        fields = ["q", "order_by"]

    def filter_q(self, queryset: QuerySet, name: str, value: str) -> QuerySet:
        return queryset.filter(
            Q(body__icontains=value)
            | Q(user__first_name__icontains=value)
            | Q(user__last_name__icontains=value)
            | Q(user__email__icontains=value)
        )

    def filter_queryset(self, queryset: QuerySet) -> QuerySet:
        ordering = self.form.cleaned_data.get("order_by") or []
        for alias in {value.lstrip("-") for value in ordering} & _ORDERING_ANNOTATIONS.keys():
            service = shared_services.get(_ORDERING_ANNOTATIONS[alias])
            if service and alias not in queryset.query.annotations:
                queryset = queryset.annotate(
                    **{alias: service.get_annotations(queryset.model)[alias]}
                )
        return super().filter_queryset(queryset)
