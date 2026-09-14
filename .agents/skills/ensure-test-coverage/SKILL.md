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

## Rules

1. **Never run on the host.** All pytest and coverage commands run inside the container.
2. **Never mark a task complete if coverage < 75%.**
3. **Prefer real behavior over mocks.** Mock only external I/O (HTTP, S3, email) — never the DB.
4. **Bug fixes → regression test first.** Write a failing test reproducing the bug, then fix it.
5. **Follow project test layout.** Place tests under `baseapp_<package>/tests/`, using `integration/` and `unit/` when working on packages or `apps/<app>/tests/integration/` or `apps/<app>/tests/unit/` when working on a project or template. Use `factories.py` and `fixtures.py`.
6. **Both API surfaces need coverage.** REST + GraphQL features both need tests.
7. **Don't over-test boilerplate.** Skip `__str__`, auto-generated migrations. Focus on logic, permissions, and edge cases.

