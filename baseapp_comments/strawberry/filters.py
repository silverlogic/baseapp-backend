from django.db.models import QuerySet

from baseapp_core.plugins import shared_services

from ..graphql import filters as graphene_filters

# Ordering aliases and the metadata service that annotates each one.
_ORDERING_ANNOTATIONS = {
    "replies_count_total": "commentable_metadata",
    "reactions_count_total": "reactable_metadata",
}


class CommentFilter(graphene_filters.CommentFilter):
    """Graphene's CommentFilter, annotating an ordering alias only when it is ordered by.

    Graphene annotates every Comment queryset in `pre_optimization_hook`.
    """

    def filter_queryset(self, queryset: QuerySet) -> QuerySet:
        ordering = self.form.cleaned_data.get("order_by") or []
        for alias in {value.lstrip("-") for value in ordering} & _ORDERING_ANNOTATIONS.keys():
            service = shared_services.get(_ORDERING_ANNOTATIONS[alias])
            if service and alias not in queryset.query.annotations:
                queryset = queryset.annotate(
                    **{alias: service.get_annotations(queryset.model)[alias]}
                )
        return super().filter_queryset(queryset)
