from typing import Optional

from django.db.models import QuerySet
from query_optimizer.compiler import OptimizationCompiler, optimize
from query_optimizer.typing import GQLInfo, TModel


def optimize_without_evaluation(
    queryset: QuerySet[TModel],
    info: GQLInfo,
    *,
    max_complexity: Optional[int] = None,
) -> QuerySet[TModel]:
    optimizer = OptimizationCompiler(info, max_complexity=max_complexity).compile(queryset)
    if optimizer is not None:
        queryset = optimizer.optimize_queryset(queryset)
    return queryset


def safe_optimize(
    root: TModel,
    info: GQLInfo,
    queryset: QuerySet[TModel],
    *,
    max_complexity: Optional[int] = None,
    evaluate: bool = True,
) -> QuerySet[TModel]:
    """
    If root is the same as queryset.model, most likely the queryset is already optimized.
    That's because get_node optimizes the main queryset, therefore it optimizes the root object.

    Re-optimizing a queryset causes issues when runnign the AST algorithm.
    """
    if root.__class__ == queryset.model:
        return queryset

    if evaluate:
        return optimize(queryset, info, max_complexity=max_complexity)
    else:
        return optimize_without_evaluation(queryset, info, max_complexity=max_complexity)
