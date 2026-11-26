"""
Test helpers for counting database queries. None of them needs GraphQL.

- `assert_queries_dont_grow`: lists; fails when the query count grows with the data.
- `assert_max_queries`: single objects and absolute budgets; a capture window.
- `capture_database_queries` / `QueryData`: the capture both count with.
"""

from .queries import QueryData, capture_database_queries
from .query_counts import QueryBudget, assert_max_queries, assert_queries_dont_grow

__all__ = [
    "QueryBudget",
    "QueryData",
    "assert_max_queries",
    "assert_queries_dont_grow",
    "capture_database_queries",
]
