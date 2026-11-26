# Query-Count Regression Tests

An optimization nobody asserts on is an optimization that will be removed by accident. Because
N+1s here are silent — correct data, wrong query count — the test *is* the specification.

**Every list path a block exposes should have one.** This repo uses no
`django_assert_num_queries` and no `assertNumQueries`.

## Start here: the two helpers

`baseapp_core.graphql.testing` ships two assertions that cover styles 1 to 3 below in one call
each. Reach for them first; write the hand-rolled forms only for SQL-shape checks (style 4) or
when you need the exact numbered breakdown of style 1.

```python
from baseapp_core.graphql.testing import assert_max_queries, assert_queries_dont_grow
```

**Lists: `assert_queries_dont_grow`.** Runs the operation with `small` items (1), then `big`
(20), and fails when the count grows by more than `per_item` per extra item. This is the check
that catches an N+1, and it doesn't break when someone adds a field.

```python
def test_members_dont_grow(graphql_user_client, django_user_client) -> None:
    profile = django_user_client.user.profile

    assert_queries_dont_grow(
        run=lambda: graphql_user_client(
            MEMBERS_QUERY,
            variables={"id": profile.relay_id},
            headers={"HTTP_CURRENT_PROFILE": profile.relay_id},
        ),
        add_items=lambda n: ProfileUserRoleFactory.create_batch(n, profile=profile),
        hint="resolve_members started querying per row",
    )
```

`per_item=0` (the default) is the strict check. An N+1 you accept gets `per_item=k` and a
comment saying why and which story removes it: the bound is still enforced, so the list can't
get worse. `add_items(n)` runs outside the capture.

**Single objects: `assert_max_queries`.** A capture window, not a runner: wrap the request the
test already makes and keep asserting on its response. No second request.

```python
def test_profile_page(graphql_user_client, profile) -> None:
    with assert_max_queries(12, hint="the profile lost one of its metadata annotations"):
        response = graphql_user_client(PROFILE_PAGE_QUERY, variables={"id": profile.relay_id})
    assert response.json()["data"]["profile"]["name"] == profile.name
```

It also works as a decorator (`@assert_max_queries(12)`), which counts the whole test body:
fixtures run before the window opens, but factories called in the body are counted, so use
`with` when the body creates data.

Both helpers:

- count with `capture_database_queries()`, so their numbers match `QueryData`'s (transaction
  statements and constance reads excluded);
- clear the ContentType cache before each capture, so counts don't depend on test order;
- print the counts, the `hint` as "Likely cause", and every captured query with its SQL and
  abridged stack when they fail. Write the hint the way style 2 writes its ranked causes;
- work with any client fixture and any headers (`Current-Profile` included).

`assert_queries_dont_grow` also fails on a response with GraphQL `errors` or an error status,
before comparing counts: a request that errors out early runs few queries and would otherwise
pass. The capture window can't see the response, so assert on the data after it.

`baseapp_profiles/tests/test_graphql_query_counts.py` uses both.

The styles below are what the helpers replace, and what existing tests still use.

## Style 1 — exact count with a per-query explanation

Use `graphql_client_with_queries` (from `baseapp_core/graphql/testing/fixtures.py`) when you can
enumerate every query. It returns `(response, QueryData)`; `QueryData` records interpolated SQL
plus an abridged stack per query, and `queries.log` pretty-prints them.

`baseapp_auth/tests/graphql/test_queries_user.py:186`:

```python
def test_anon_can_query_users_list_with_optimized_query_with_public_id(
    graphql_client_with_queries,
) -> None:
    UserFactory.create_batch(10)
    ContentType.objects.clear_cache()
    response, queries = graphql_client_with_queries(QUERY_USERS_LIST)
    content = response.json()

    assert queries.count == 7
    assert len(content["data"]["users"]["edges"]) == 10

    # With optimizer queries are expected to be 7:
    # 1. ContentType lookup for users.user (cold-cache; cached after first request in production)
    # 2. ContentType lookup for profiles.profile (cold-cache; same caching as above)
    # 3. SELECT users_user with _ratable_* Subqueries inlined by
    #    AbstractUserObjectType.pre_optimization_hook (RatableMetadataService.annotate_queryset)
    # 4. SELECT profiles_profile with _commentable_*, _followable_*, mapped_public_id Subqueries
    #    inlined by ProfileObjectType.pre_optimization_hook
    # 5. SELECT COUNT(*) for pagination
    # 6. Same as #3 with LIMIT 10 for the returned page slice
    # 7. Same as #4 for the page's profiles
```

The numbered comment is the valuable part. When the count changes, the next person can tell which
query appeared instead of re-deriving the whole path.

**`ContentType.objects.clear_cache()` before the capture** — otherwise the count depends on test
ordering, since the ContentType manager caches across tests.

## Style 2 — upper bound with ranked failure causes

Use `CaptureQueriesContext` when the exact count churns with optimizer internals but the *shape*
must hold. `baseapp_chats/tests/test_graphql_query_counts.py`:

```python
    with CaptureQueriesContext(connection) as ctx:
        response = graphql_user_client(
            ROOM_MESSAGES_WITH_MENTIONS, variables={"roomId": room.relay_id}
        )

    assert "errors" not in response.json(), response.json()
    # ~17 queries today, comparable to the comments+mentions baseline.
    # 20 absorbs minor optimiser-internals shifts; trips immediately
    # on any of the three regressions named in the docstring.
    assert len(ctx.captured_queries) <= 20, (
        f"Messages-with-mentions listing issued {len(ctx.captured_queries)} queries. "
        "Likely causes (in priority order):\n"
        "  - `chatRoom.allMessages` reverted to `DjangoFilterConnectionField`\n"
        "  - `BaseMessageObjectType.pre_optimization_hook` dropped one of "
        "`room_id` / `deleted` / `message_type` from `only_fields`\n"
        "  - `MentionsInterface.mentions.optimizer_hook` was lost\n"
        "  - Message ObjectType lost its `document = GenericRelation(DocumentId)`"
    )
```

**Always write the ranked "likely causes" message.** A bare `assert count <= 20` tells the next
person nothing; this one names the four things that could have broken, in priority order. The test
docstring goes further and quantifies each: *"missing (1) → ~54; missing (3) → ~32; missing (2) →
fan-out as messages × mentions."*

## Style 3 — the strongest assertion: doubling the data changes nothing

An absolute count catches drift. Only a volume comparison proves there is no per-row fan-out.
`baseapp_blocks/tests/test_graphql_queries_object_blocks.py`:

```python
    assert big_count == small_count, (
        f"N+1: {small_count} queries for 3 blocks vs {big_count} for 20 "
        f"(delta {big_count - small_count} over 17 extra blocks = "
        f"{(big_count - small_count) / 17:.1f} per row)"
    )
    assert small_count == EXPECTED_BLOCKS_INTERFACE_NESTED_LIST_QUERY_COUNT
```

Pair it with a named budget constant so both counts rising together can't slip through:

```python
# Absolute query budgets for the COUNTS_ONLY_QUERY path. These guard against
# regressions where BOTH the small- and big-volume counts bump together (which
# the per-test `big == small` assertion would miss). Bump these deliberately if
# you change the resolver / annotation / middleware path and the new total is
# the new normal — don't bump them to silence a failure without first
# understanding which extra query was added.

EXPECTED_BLOCKS_INTERFACE_QUERY_COUNT = 6
EXPECTED_BLOCKS_INTERFACE_PERM_DENIED_UPPER_BOUND = 10
EXPECTED_BLOCKS_INTERFACE_NESTED_LIST_QUERY_COUNT = 9
```

That comment is the policy: **a failing budget is investigated, not raised.**

## Style 4 — SQL-shape assertions

When a count is too coarse, assert on the SQL itself. Batching:

```python
    prefetch_queries = [
        q for q in sql if "_unreadmessagecount" in q.lower() and 'room_id" in' in q.lower()
    ]
    assert len(prefetch_queries) <= 1, (
        f"`unread_messages` prefetch ran {len(prefetch_queries)} times; "
        "expected a single batched IN query. ..."
    )
```

Write-path shape, `baseapp_follows/tests/test_follow_count.py:117`:

```python
    follow_count_queries = [q for q in sql if "COUNT(*)" in q.upper() and "follows_follow" in q]
    assert follow_count_queries == [], (
        "Save path is doing a COUNT(*) on follows_follow — should be using F+1 "
        f"instead. Offending queries: {follow_count_queries}"
    )
    assert not any("FOR UPDATE" in q.upper() for q in sql), (
        "Save path is acquiring SELECT FOR UPDATE on FollowableMetadata — should "
        f"be a lock-free F-expression UPDATE. Captured queries: {sql}"
    )
```

Helper used throughout:

```python
def _captured_sql(ctx) -> list[str]:
    return [q["sql"] for q in ctx.captured_queries]
```

## Picking a style

| Situation | Use |
|---|---|
| A list or connection: proving absence of fan-out | `assert_queries_dont_grow` (style 3) |
| A single object, or a count that churns with optimizer internals | `assert_max_queries` with a `hint` (style 2) |
| Stable path where every query should be explained | style 1 — exact count + numbered comment |
| Batching / write-path shape | style 4 — filter the captured SQL |

Styles 2 and 3 combine well: `small, big = assert_queries_dont_grow(...)` returns both
`QueryData`, so a test can also pin `small.count` to a named budget.

## Where these live

`baseapp_chats/tests/test_graphql_query_counts.py` is the best-documented example and names its own
lineage in the module docstring. Others:
`baseapp_comments/tests/test_graphql_queries_object_comments.py` (pastes the full expected SQL per
query), `baseapp_follows/tests/test_graphql_queries_object_follows.py`,
`baseapp_mentions/tests/test_graphql_queries_object_mentions.py` (asserts delta is exactly zero),
`baseapp_reactions/`, `baseapp_ratings/`, `baseapp_reports/`, `baseapp_blocks/`.

## Checklist for a new block

- One test per list path the block exposes.
- One test per shared-interface field carrying an `optimizer_hook`, asserting it fires only when
  selected.
- A small-vs-big volume comparison on any connection.
- If the block degrades without an optional dependency, a test with that app absent — use
  `with_disabled_apps` / `with_disabled_apps_context` from `baseapp_core/plugins/tests/fixtures.py`
  and put it in `tests/integration/`.

## Running them

Run from the **submodule** root, not a consuming template, and go through **`uv run`**:

```bash
docker compose run --rm web uv run --python 3.12 pytest baseapp/<name>/tests/ --reuse-db
```

**`uv run` is not optional, and bare `pytest` is a trap.** The image is built with
`uv sync --no-install-project`, so the `baseapp_backend` distribution is *not* installed in
`/opt/venv`. Plugin discovery is `stevedore` over the `baseapp.plugins` entry-point namespace
(`baseapp_core/plugins/registry.py`) with no fallback, so without an installed distribution
exactly **one** entry point is visible (`testproject_plugin_test_app`), no plugin's settings or
GraphQL roots are aggregated, and tests fail in confusing ways. `uv run` builds and installs the
project first, which registers all entry points. CI does the same thing.

Bare `pytest` *appears* to work once you have run `uv run` before, because that leaves a
gitignored `baseapp_backend.egg-info/` in the bind-mounted source tree which `importlib.metadata`
picks up from the working directory. Delete it, or start from a fresh checkout, and bare `pytest`
breaks again. Don't rely on it.

The explicit `--python 3.12` is no longer required — `.python-version` now matches
`requires-python = ">=3.12"` — but it is harmless and kept here so the command still works on
checkouts made before that alignment, where plain `uv run` aborts with
`No interpreter found for Python 3.11`.

### Diagnosing a suspicious run

If every test in a new block fails at once, check plugin discovery before debugging your code:

```bash
docker compose run --rm web uv run --python 3.12 python -c \
  "from importlib.metadata import entry_points; \
   print(len(list(entry_points(group='baseapp.plugins'))))"
```

Expect ~25. If it prints `1`, the distribution isn't installed — that is the bug, not your test.

## Anti-patterns

- Raising a budget constant to make a red test green without identifying the added query.
- Omitting `ContentType.objects.clear_cache()`, making counts order-dependent.
- A bare `assert count <= N` with no explanation of what N is made of.
- Asserting only an absolute count with no volume comparison — an N+1 that is small at 3 rows
  passes.
- Testing only the happy path when the resolver branches on an optional service being present.
- Writing the test after merging the optimization. Capture the count before and after; the
  difference is the evidence the change did anything.
