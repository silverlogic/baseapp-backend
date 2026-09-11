# Query-Count Regression Tests

An optimization nobody asserts on is an optimization that will be removed by accident. Because
N+1s here are silent — correct data, wrong query count — the test *is* the specification.

**Every list path a block exposes should have one.** This repo uses no
`django_assert_num_queries` and no `assertNumQueries`; there are two house styles.

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

| Situation | Style |
|---|---|
| Stable path you can fully enumerate | 1 — exact count + numbered comment |
| Count churns with optimizer internals | 2 — upper bound + ranked causes |
| Proving absence of fan-out | 3 — small vs big, plus a named budget |
| Batching / write-path shape | 4 — filter the captured SQL |

Styles 2 and 3 combine well: assert `big == small` *and* `small == BUDGET`.

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

The explicit `--python 3.12` is also required: `.python-version` in the repo root still pins
`3.11` while `pyproject.toml` sets `requires-python = ">=3.12"`, so plain `uv run` aborts with
`No interpreter found for Python 3.11`. CI passes `--python` explicitly for the same reason.

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
