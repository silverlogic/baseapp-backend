---
name: run-development-commands
version: 1.2.0
description: Translate developer intent into the correct Docker Compose commands for this Django project. Always use this skill when the user wants to run tests, start the dev server, make or apply migrations, open a Django or database shell, lint or format code, run any manage.py command, install or add a Python dependency, audit dependencies, or execute any other development command — even when they don't mention Docker explicitly.
triggers:
  - run tests
  - run server
  - make migrations
  - apply migrations
  - run lint
  - format code
  - open shell
  - manage.py
  - django command
  - docker compose run
  - pytest
  - install package
  - add dependency
  - uv add
config:
  service: web
  compose_file: docker-compose.yml
---

# run-development-commands

## Purpose

All commands must run inside the `web` Docker service. Never run Python, pytest, or Django management commands directly on the host.

**Always detect container state before constructing a command:**

```bash
docker compose ps --status running --services | grep -qx web
```

- Running → use `exec` → `docker compose exec web <command>`
- Stopped → use `run --rm` → `docker compose run --rm web <command>`

In all patterns below, `<run>` is the subcommand form (`exec` or `run --rm`); the service name `web` is written explicitly in each template.

---

## Command Patterns

### Development Server

```bash
docker compose up          # all services (postgres, redis, rabbitmq, web, worker, scheduler)
docker compose up web      # web only
```

### Tests

```bash
docker compose <run> web pytest
docker compose <run> web pytest apps/<app>/tests/
docker compose <run> web pytest apps/<app>/tests/test_file.py::test_function
docker compose <run> web pytest baseapp_<package>/tests/
docker compose <run> web pytest baseapp_<package>/tests/test_file.py::test_function
docker compose <run> web pytest -k "some_name"
docker compose <run> web pytest --reuse-db
docker compose <run> web pytest --cov="apps" --junitxml=test-reports/junit.xml tests
docker compose <run> web pytest --cov="baseapp_<package>" --junitxml=test-reports/junit.xml baseapp_<package>/tests
```

### Migrations

```bash
docker compose <run> web python manage.py makemigrations [<app_label>]
docker compose <run> web python manage.py migrate [<app_label>]
docker compose <run> web python manage.py showmigrations
```

### Lint & Format

```bash
docker compose <run> web black .          # line-length=100
docker compose <run> web isort .
docker compose <run> web flake8 .
docker compose <run> web ast-grep scan --globs '!baseapp-backend'   # code-guideline rules (shared from baseapp-backend/.ast-grep/); the submodule is linted in its own CI
docker compose <run> web ast-grep test    # test the ast-grep rules themselves
docker compose <run> web pre-commit run --all-files
```

### Shells

```bash
docker compose <run> web python manage.py shell
docker compose <run> web python manage.py dbshell
```

### Dependencies (uv)

```bash
docker compose <run> web uv add <package>          # add a new dependency
docker compose <run> web uv add <package>==<ver>   # pin to a specific version
docker compose <run> web uv add --dev <package>    # add a dev-only dependency
docker compose <run> web uv sync                   # sync all dependencies from lockfile
```

### Other

```bash
docker compose <run> web python manage.py collectstatic --noinput
docker compose <run> web pip-audit
docker compose <run> web python manage.py <command> [args]
```

---

## Rules

1. **Never run on the host.** All Python, pytest, Black, Flake8, manage.py, and uv commands run inside the container.
2. **Use `uv` for all dependency changes.** Never use `pip install` — always `uv add` inside Docker.
3. **Always detect container state first.** Never hardcode `exec` or `run --rm`.
4. **Destructive commands need confirmation.** Before `migrate` on a non-local environment, `flush`, `reset`, or any data-modifying command, confirm with the user.
5. **Clarify ambiguous requests and don't assume host env.** "run the app" → default to `docker compose up`; all env is injected by Docker Compose from `.env`.

---

## Edge Cases

**Unknown command** → check container state, then wrap as `exec web` or `run --rm web`.

**"Run tests faster"** → add `--reuse-db`.

**Check for missing migrations** → `docker compose <run> web python manage.py migrate --check` (exits non-zero if unapplied migrations exist).
