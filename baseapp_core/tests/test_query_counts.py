import pytest
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.http import HttpResponse, JsonResponse

from baseapp_core.testing import (
    QueryBudget,
    assert_max_queries,
    assert_queries_dont_grow,
)
from baseapp_core.tests.factories import UserFactory

pytestmark = pytest.mark.django_db

User = get_user_model()

USERS_QUERY = """
    query Users {
        users {
            edges {
                node {
                    id
                }
            }
        }
    }
"""


def run_queries(count: int) -> None:
    for _ in range(count):
        User.objects.exists()


def list_users(queries_per_row: int = 0) -> HttpResponse:
    """One query for the list, then `queries_per_row` more for each user: an N+1 on demand."""
    users = list(User.objects.all())
    for user in users:
        for _ in range(queries_per_row):
            User.objects.filter(pk=user.pk).exists()
    return JsonResponse({"data": {"count": len(users)}})


def add_users(count: int) -> None:
    UserFactory.create_batch(count)


class TestAssertMaxQueries:
    def test_passes_at_the_limit(self) -> None:
        with assert_max_queries(3) as budget:
            run_queries(3)

        assert isinstance(budget, QueryBudget)
        assert budget.queries.count == 3

    def test_fails_over_the_limit_with_hint_and_queries(self) -> None:
        with pytest.raises(AssertionError) as error:
            with assert_max_queries(1, hint="the list lost its select_related"):
                run_queries(3)

        message = str(error.value)
        assert "Expected at most 1 queries, ran 3." in message
        assert "Likely cause: the list lost its select_related" in message
        assert ">>> Queries (3):" in message
        assert '"users_user"' in message
        assert "--- Stack (abridged)" in message

    def test_no_hint_line_without_a_hint(self) -> None:
        with pytest.raises(AssertionError) as error:
            with assert_max_queries(0):
                run_queries(1)

        assert "Likely cause" not in str(error.value)

    def test_counts_only_inside_the_window(self) -> None:
        run_queries(5)
        with assert_max_queries(1) as budget:
            run_queries(1)
        run_queries(5)

        assert budget.queries.count == 1

    def test_lets_an_error_inside_the_window_through(self) -> None:
        with pytest.raises(ValueError, match="boom"):
            with assert_max_queries(0):
                run_queries(2)
                raise ValueError("boom")

    def test_clears_the_contenttype_cache(self) -> None:
        ContentType.objects.get_for_model(User)
        with assert_max_queries(1) as budget:
            ContentType.objects.get_for_model(User)

        assert budget.queries.count == 1

    def test_rejects_a_negative_limit(self) -> None:
        with pytest.raises(ValueError, match="zero or more"):
            assert_max_queries(-1)

    def test_works_with_a_graphql_client(self, graphql_client) -> None:
        UserFactory.create_batch(2)
        with assert_max_queries(20) as budget:
            response = graphql_client(USERS_QUERY)

        assert len(response.json()["data"]["users"]["edges"]) == 2
        assert budget.queries.count > 0


class TestAssertMaxQueriesAsDecorator:
    @assert_max_queries(2)
    def test_passes_within_the_limit(self) -> None:
        run_queries(2)

    @assert_max_queries(20)
    def test_keeps_the_fixtures(self, graphql_client) -> None:
        response = graphql_client(USERS_QUERY)
        assert "errors" not in response.json()

    def test_fails_over_the_limit(self) -> None:
        @assert_max_queries(1, hint="decorated")
        def operation() -> None:
            run_queries(3)

        with pytest.raises(AssertionError, match="Expected at most 1 queries, ran 3."):
            operation()

    def test_each_call_gets_its_own_window(self) -> None:
        @assert_max_queries(2)
        def operation() -> None:
            run_queries(2)

        operation()
        operation()


class TestAssertQueriesDontGrow:
    def test_passes_when_the_count_stays_flat(self) -> None:
        small, big = assert_queries_dont_grow(run=list_users, add_items=add_users)

        assert small.count == big.count == 1

    def test_fails_on_an_n_plus_one(self) -> None:
        with pytest.raises(AssertionError) as error:
            assert_queries_dont_grow(
                run=lambda: list_users(queries_per_row=1),
                add_items=add_users,
                hint="users lost their prefetch",
            )

        message = str(error.value)
        assert "2 queries for 1 items, 21 for 20" in message
        assert "19 more for 19 extra items, 1.0 per item; allowed 0, 0 per item" in message
        assert "Likely cause: users lost their prefetch" in message
        assert "Queries for 20 items:" in message
        assert ">>> Queries (21):" in message

    def test_accepts_a_declared_linear_bound(self) -> None:
        small, big = assert_queries_dont_grow(
            run=lambda: list_users(queries_per_row=1),
            add_items=add_users,
            per_item=1,
        )

        assert big.count - small.count == 19

    def test_fails_when_growth_passes_the_declared_bound(self) -> None:
        with pytest.raises(AssertionError, match="2.0 per item; allowed 19, 1 per item"):
            assert_queries_dont_grow(
                run=lambda: list_users(queries_per_row=2),
                add_items=add_users,
                per_item=1,
            )

    def test_custom_sizes(self) -> None:
        calls = []

        def add_items(count: int) -> None:
            calls.append(count)
            add_users(count)

        assert_queries_dont_grow(run=list_users, add_items=add_items, small=2, big=5)

        assert calls == [2, 3]

    def test_fails_on_graphql_errors_before_counting(self, graphql_client) -> None:
        with pytest.raises(AssertionError, match="returned errors"):
            assert_queries_dont_grow(
                run=lambda: graphql_client("query { users { edges { node { notAField } } } }"),
                add_items=add_users,
            )

    def test_fails_on_an_error_status(self) -> None:
        with pytest.raises(AssertionError, match="failed with status 403"):
            assert_queries_dont_grow(
                run=lambda: HttpResponse("forbidden", status=403),
                add_items=add_users,
            )

    def test_works_with_a_graphql_client(self, graphql_client) -> None:
        small, big = assert_queries_dont_grow(
            run=lambda: graphql_client(USERS_QUERY),
            add_items=add_users,
            per_item=5,
        )

        assert small.count > 0
        assert big.count > 0

    @pytest.mark.parametrize(
        ("kwargs", "message"),
        [
            ({"small": 5, "big": 5}, "less than big"),
            ({"small": -1}, "less than big"),
            ({"per_item": -1}, "per_item must be zero or more"),
        ],
    )
    def test_rejects_bad_arguments(self, kwargs, message) -> None:
        with pytest.raises(ValueError, match=message):
            assert_queries_dont_grow(run=list_users, add_items=add_users, **kwargs)


def test_capture_is_still_importable_from_graphql_utils() -> None:
    """`capture_database_queries` and `QueryData` moved to `baseapp_core.testing`; projects that
    import them from `baseapp_core.graphql.utils` keep working."""
    from baseapp_core.graphql import utils
    from baseapp_core.testing import QueryData, capture_database_queries

    assert utils.capture_database_queries is capture_database_queries
    assert utils.QueryData is QueryData
