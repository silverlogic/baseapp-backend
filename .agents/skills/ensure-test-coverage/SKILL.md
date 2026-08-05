---
name: ensure-test-coverage
version: 1.1.0
description: Ensure every code change ships with passing tests and ≥ 75% coverage before marking a task complete. Always use this skill when implementing a feature, fixing a bug, refactoring backend code, or about to mark any task done — even if the user doesn't ask for tests explicitly.
triggers:
  - writing new code
  - modifying backend logic
  - before completing a task
  - implementing a feature
  - fixing a bug
  - refactoring
config:
  threshold: 75
  service: web
  compose_file: docker-compose.yml
---

# ensure-test-coverage

## Purpose

No task is complete until the test suite passes and coverage is ≥ 75%. All commands run inside the `web` Docker service — never on the host.

Check container state first: `docker compose ps --status running --services | grep -qx web`
- Running → `docker compose exec web <command>`
- Stopped → `docker compose run --rm web <command>`

(`<run>` below means whichever form applies.)

---

## Workflow

1. Write or update tests alongside the implementation.
2. Run: `docker compose <run> web pytest --cov --cov-report=term-missing`
3. Coverage ≥ 75% and all tests pass → done.
4. Coverage < 75% → read the missing-lines report, add targeted tests, re-run. Repeat.

---

## Commands

```bash
docker compose <run> web pytest --cov --cov-report=term-missing    # recommended
docker compose <run> web pytest --cov --reuse-db                   # faster re-runs
```

---

## Parallel-safe tests (required)

CI **and** local run the suite under `pytest-xdist` (`-n 2 --dist loadscope`, per `setup.cfg`) — each worker gets its **own** test DB. Tests must be **hermetic**:

**Don't depend on *global* reference data your test didn't establish** — migration-seeded rows, or rows left by other tests. A `TransactionTestCase` truncates every table (Django does not restore migration data without `serialized_rollback`), and under xdist that wipe can land on your worker just before your test — so global-reference assertions pass serially but flake in parallel.

Data you set up **in your own scope is fine**: the test function, a Django `setUpTestData`, or a module/class-scoped fixture. `--dist loadscope` keeps a whole module on one worker, so same-scope setup stays put — the trap is *global* seed data, not shared local setup. (This safety leans on `loadscope`; don't switch the dist mode without accounting for it.)

❌ Flaky — depends on migration-seeded rows:
```python
def test_list_report_types(graphql_client):
    resp = graphql_client(REPORT_TYPES_QUERY, variables={"topLevelOnly": True})
    assert len(resp.json()["data"]["allReportTypes"]["edges"]) == 8
```

✅ Hermetic — creates its own rows, asserts membership not counts:
```python
def test_list_report_types(graphql_client):
    top = ReportTypeFactory(key="qa_top")
    ReportTypeFactory(key="qa_sub", parent_type=top)      # a subtype
    resp = graphql_client(REPORT_TYPES_QUERY, variables={"topLevelOnly": True})
    keys = {e["node"]["key"] for e in resp.json()["data"]["allReportTypes"]["edges"]}
    assert "qa_top" in keys
    assert "qa_sub" not in keys                            # independent of ambient data
```

Create your own rows (factories + explicit keys); assert **membership**, not global counts. **Reproduce any parallel failure serially before deciding it's real:** `pytest -n 0 path::test`.

---

## Rules

1. **Never run on the host.** All pytest and coverage commands run inside the container.
2. **Never mark a task complete if coverage < 75%.**
3. **Prefer real behavior over mocks.** Mock only external I/O (HTTP, S3, email) — never the DB.
4. **Bug fixes → regression test first.** Write a failing test reproducing the bug, then fix it.
5. **Follow project test layout.** Place tests under `baseapp_<package>/tests/`, using `integration/` and `unit/` when working on packages or `apps/<app>/tests/integration/` or `apps/<app>/tests/unit/` when working on a project or template. Use `factories.py` and `fixtures.py`.
6. **Both API surfaces need coverage.** REST + GraphQL features both need tests.
7. **Don't over-test boilerplate.** Skip `__str__`, auto-generated migrations. Focus on logic, permissions, and edge cases.
8. **Tests must be parallel-safe (hermetic).** See "Parallel-safe tests" above — never assert on migration-seeded or cross-test data; create and assert on your own rows (membership, not global counts).

