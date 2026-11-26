"""
Query-count assertions for tests.

Two helpers over `capture_database_queries()`, so their counts match the exact-count tests that
already use `QueryData` (transaction statements and constance reads are not counted):

- `assert_max_queries(n)`: a capture window around the request a test already makes, as a
  `with` block or a decorator. Fails when more than `n` queries ran inside it.
- `assert_queries_dont_grow(run, add_items)`: runs an operation at two data sizes and fails
  when the count grows faster than a declared bound (none by default). This is the check that
  catches an N+1; use it for lists and `assert_max_queries` for single objects.

Both print every captured query with its SQL and abridged stack on failure, after an optional
`hint` naming the likely cause.
"""

import json
from collections.abc import Callable
from contextlib import ContextDecorator, ExitStack
from types import TracebackType

from django.contrib.contenttypes.models import ContentType
from django.http import HttpResponse

from .queries import QueryData, capture_database_queries


def _hint_line(hint: str) -> str:
    return f"\nLikely cause: {hint}" if hint else ""


class QueryBudget(ContextDecorator):
    """
    A capture window: `with assert_max_queries(5) as budget:` or `@assert_max_queries(5)`.

    `queries` holds the captured `QueryData` once the window has opened, so a test can also
    assert on the SQL. Used as a decorator, each call of the decorated function gets its own
    window.
    """

    queries: QueryData

    def __init__(self, max_queries: int, *, hint: str = "") -> None:
        if max_queries < 0:
            raise ValueError("max_queries must be zero or more")
        self.max_queries = max_queries
        self.hint = hint
        self._stack = ExitStack()

    def _recreate_cm(self) -> "QueryBudget":
        # ContextDecorator reuses `self` across calls by default; a fresh window per call keeps
        # one test's queries out of the next.
        return QueryBudget(self.max_queries, hint=self.hint)

    def __enter__(self) -> "QueryBudget":
        # The ContentType manager caches across tests, so without this the count depends on
        # which tests ran first.
        ContentType.objects.clear_cache()
        self._stack = ExitStack()
        self.queries = self._stack.enter_context(capture_database_queries())
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool:
        self._stack.close()
        # An error raised inside the window is the more useful failure; let it through.
        if exc_type is None and self.queries.count > self.max_queries:
            raise AssertionError(
                f"Expected at most {self.max_queries} queries, ran {self.queries.count}."
                f"{_hint_line(self.hint)}"
                f"{self.queries.log}"
            )
        return False


def assert_max_queries(max_queries: int, *, hint: str = "") -> QueryBudget:
    """
    Fail when the code inside the window runs more than `max_queries` queries.

    The window counts what runs inside it and nothing else: wrap the request the test already
    makes and keep asserting on its response. As a decorator it counts the whole test body;
    fixtures run before the window opens, but factories called in the body are counted.

        with assert_max_queries(6, hint="profile lost its select_related"):
            response = graphql_user_client(PROFILE_QUERY, variables={"id": profile.relay_id})
        assert response.json()["data"]["profile"]["name"] == profile.name
    """
    return QueryBudget(max_queries, hint=hint)


def _assert_no_errors(response: HttpResponse) -> None:
    """
    Fail on an error response. A request that errors out early runs few queries, so without
    this check a broken operation would pass a query-count assertion.
    """
    content = None
    if "json" in response.get("Content-Type", ""):
        # Decode the body rather than call `.json()`, which only test-client responses have.
        content = json.loads(response.content)
    if isinstance(content, dict) and content.get("errors"):
        raise AssertionError(f"The operation returned errors: {content['errors']}")
    if response.status_code >= 400:
        raise AssertionError(
            f"The operation failed with status {response.status_code}: {content or response}"
        )


def _measure(run: Callable[[], HttpResponse]) -> QueryData:
    ContentType.objects.clear_cache()
    with capture_database_queries() as queries:
        response = run()
    _assert_no_errors(response)
    return queries


def assert_queries_dont_grow(
    run: Callable[[], HttpResponse],
    add_items: Callable[[int], object],
    *,
    small: int = 1,
    big: int = 20,
    per_item: int = 0,
    hint: str = "",
) -> tuple[QueryData, QueryData]:
    """
    Run `run()` with `small` items, then with `big`, and fail if the query count grows by more
    than `per_item` for each extra item.

    `add_items(n)` creates `n` more items; it runs outside the capture. `per_item=0` is the
    strict "no N+1" check. `per_item=1` declares an accepted N+1 with a linear bound: it still
    fails if the list gets worse. Returns the `QueryData` of both runs.

        assert_queries_dont_grow(
            run=lambda: graphql_user_client(MEMBERS_QUERY, variables={"id": profile.relay_id}),
            add_items=lambda n: ProfileUserRoleFactory.create_batch(n, profile=profile),
            hint="resolve_members lost its select_related",
        )
    """
    if not 0 <= small < big:
        raise ValueError("small must be zero or more and less than big")
    if per_item < 0:
        raise ValueError("per_item must be zero or more")

    add_items(small)
    small_queries = _measure(run)
    add_items(big - small)
    big_queries = _measure(run)

    extra_items = big - small
    growth = big_queries.count - small_queries.count
    allowed = per_item * extra_items
    if growth > allowed:
        raise AssertionError(
            f"Query count grew with the data: {small_queries.count} queries for {small} items, "
            f"{big_queries.count} for {big} ({growth} more for {extra_items} extra items, "
            f"{growth / extra_items:.1f} per item; allowed {allowed}, {per_item} per item)."
            f"{_hint_line(hint)}"
            f"\nQueries for {big} items:"
            f"{big_queries.log}"
        )
    return small_queries, big_queries
