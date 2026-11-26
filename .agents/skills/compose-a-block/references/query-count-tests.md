# Query-Count Regression Tests

An optimization nobody asserts on is an optimization that will be removed by accident. Because
N+1s here are silent — correct data, wrong query count — the test *is* the specification.

**Every list path a block exposes should have one.** Every count in this repo goes through the
two helpers below: no `queries.count == N`, no `len(ctx.captured_queries)`, no
`django_assert_num_queries`. One pattern means one way to read a failure.

## The two helpers

```python
from baseapp_core.testing import assert_max_queries, assert_queries_dont_grow
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
get worse. `add_items(n)` runs outside the capture. `small=0` covers "no rows costs the same as
some rows" (a missing metadata row falling through to `Coalesce`).

**Single objects and absolute budgets: `assert_max_queries`.** A capture window, not a runner:
wrap the request the test already makes and keep asserting on its response.

```python
def test_profile_page(graphql_user_client, profile) -> None:
    with assert_max_queries(12, hint="the profile lost one of its metadata annotations"):
        response = graphql_user_client(PROFILE_PAGE_QUERY, variables={"id": profile.relay_id})
    assert response.json()["data"]["profile"]["name"] == profile.name
```

It also works as a decorator (`@assert_max_queries(12)`), which counts the whole test body:
fixtures run before the window opens, but factories called in the body are counted, so use
`with` when the body creates data. It wraps any code, not just requests: a service method or a
queryset evaluation (`with assert_max_queries(1): rows = list(qs)`).

Both helpers:

- count with `capture_database_queries()` (transaction statements and constance reads excluded),
  which also lives in `baseapp_core.testing`. None of it needs GraphQL, so REST and service
  tests use the same helpers;
- clear the ContentType cache before each capture, so counts don't depend on test order. Budgets
  are therefore cold-cache numbers: they include the ContentType lookups;
- print the counts, the `hint` as "Likely cause", and every captured query with its SQL and
  abridged stack when they fail;
- work with any client fixture and any headers (`Current-Profile` included).

`assert_queries_dont_grow` also fails on a response with GraphQL `errors` or an error status,
before comparing counts: a request that errors out early runs few queries and would otherwise
pass. The capture window can't see the response, so assert on the data after it.

## The usual shape: growth check, then the budget

A list test pairs the two, so an N+1 and a fixed-cost regression both fail.
`baseapp_blocks/tests/test_graphql_queries_object_blocks.py`:

```python
@override_settings(ENABLE_PUBLIC_ID_LOGIC=True)
def test_block_list_with_target_blockers_count_is_flat(django_user_client, superuser_client):
    actor = ProfileFactory(owner=django_user_client.user)
    relay_id = actor.relay_id  # resolve outside the capture

    def block(n: int) -> None:
        for _ in range(n):
            target = ProfileFactory(owner=UserFactory())
            BlockFactory(actor=actor, target=target, user=django_user_client.user)

    def query():
        return superuser_client(PROFILE_BLOCKING_LIST_QUERY, variables={"id": relay_id})

    assert_queries_dont_grow(run=query, add_items=block, small=3, big=20, hint="...")

    with assert_max_queries(EXPECTED_BLOCKS_INTERFACE_NESTED_LIST_QUERY_COUNT):
        response = query()
    assert len(response.json()["data"]["node"]["blocking"]["edges"]) == 20
```

Keep these habits from the older tests:

- **Resolve relay ids outside the window.** `obj.relay_id` may look up or create the
  `DocumentId`; inside the window that query is counted and the number drifts.
- **Name the budget.** A module constant with a comment saying what it is made of, and that a
  failing budget is investigated, not raised.
- **Explain the number.** When every query can be enumerated, a numbered comment under the
  assertion (`baseapp_auth/tests/graphql/test_queries_user.py`,
  `baseapp_comments/tests/test_graphql_queries_object_comments.py`) lets the next person see
  which query appeared instead of re-deriving the path.
- **Rank the causes in the hint.** A bare budget tells the next person nothing; name the things
  that could have broken, most likely first (`baseapp_chats/tests/test_graphql_query_counts.py`).

## SQL-shape assertions

When a count is too coarse, assert on the SQL itself. These tests read the captured statements
instead of counting them. Batching:

```python
    prefetch_queries = [
        q for q in sql if "_unreadmessagecount" in q.lower() and 'room_id" in' in q.lower()
    ]
    assert len(prefetch_queries) <= 1, (
        f"`unread_messages` prefetch ran {len(prefetch_queries)} times; "
        "expected a single batched IN query. ..."
    )
```

Write-path shape, `baseapp_follows/tests/test_follow_count.py`:

```python
    follow_count_queries = [q for q in sql if "COUNT(*)" in q.upper() and "follows_follow" in q]
    assert follow_count_queries == [], (
        "Save path is doing a COUNT(*) on follows_follow — should be using F+1 "
        f"instead. Offending queries: {follow_count_queries}"
    )
```

`with assert_max_queries(n) as budget:` exposes the captured SQL as `budget.queries.queries`, so
a shape check can sit inside the same window as the count.

## Picking a helper

| Situation | Use |
|---|---|
| A list or connection | `assert_queries_dont_grow`, then `assert_max_queries` with the budget |
| A single object, a service call, a queryset evaluation | `assert_max_queries` with a `hint` |
| An accepted per-row cost | `assert_queries_dont_grow(per_item=k)` + a comment naming the fix |
| Batching / write-path shape | filter the captured SQL |

## Where these live

`baseapp_profiles/tests/test_graphql_query_counts.py` and
`baseapp_chats/tests/test_graphql_query_counts.py` are the best-documented examples. Others:
`baseapp_comments/tests/test_graphql_queries_object_comments.py` (pastes the full expected SQL per
query), `baseapp_follows/tests/test_graphql_queries_object_follows.py`,
`baseapp_mentions/tests/test_graphql_queries_object_mentions.py`, `baseapp_reactions/`,
`baseapp_ratings/`, `baseapp_reports/`, `baseapp_blocks/`, `baseapp/files/`.

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
- Counting by hand (`queries.count == N`, `len(ctx.captured_queries)`) instead of the helpers.
- Reading `obj.relay_id` inside the capture window, so the count includes a `DocumentId` lookup.
- A budget with no explanation of what N is made of.
- Asserting only an absolute count with no volume comparison — an N+1 that is small at 3 rows
  passes.
- Testing only the happy path when the resolver branches on an optional service being present.
- Writing the test after merging the optimization. Capture the count before and after; the
  difference is the evidence the change did anything.
