import logging
import subprocess
import sys
import threading
from collections.abc import Callable, Iterator
from functools import partial

import pytest
from celery.signals import task_postrun, task_prerun
from django.conf import settings
from zeal import NPlusOneError
from zeal.listeners import _nplusone_context
from zeal.signals import nplusone_detected

from baseapp_core import n_plus_one


@pytest.fixture(autouse=True)
def _clear_reported(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    # The simulated N+1s below must not land in the run's own "N+1 report (zeal)".
    monkeypatch.setattr(n_plus_one, "report", None)
    n_plus_one._reported.clear()
    yield
    n_plus_one._reported.clear()


SITE_PACKAGES = "/opt/venv/lib/python3.12/site-packages"
REPO = "/usr/src/app"  # baseapp-backend's own checkout, where its packages are not in site-packages
PROJECT = "/srv/project"  # a project's BASE_DIR
RESOLVER = f"{REPO}/baseapp_comments/graphql/object_types.py"
SERVICE = f"{REPO}/baseapp_comments/services.py"


@pytest.fixture(autouse=True)
def import_roots(monkeypatch: pytest.MonkeyPatch, settings) -> None:
    """A known sys.path and BASE_DIR, so the path rules don't depend on where the suite runs."""
    monkeypatch.setattr(
        sys, "path", [*sys.path, REPO, SITE_PACKAGES, "/usr/local/lib/python3.12", PROJECT]
    )
    settings.BASE_DIR = PROJECT


def _function_at(filename: str, name: str, calls: Callable[[], None]) -> Callable[[], None]:
    """A function whose code lives at ``filename`` (line 2) and calls ``calls``: a frame from a
    BaseApp package, a library or a test, as the detector sees it."""
    namespace = {"calls": calls}
    exec(compile(f"def {name}():\n    calls()\n", filename, "exec"), namespace)
    return namespace[name]


def _lazy_load_at(filename: str, name: str, error: NPlusOneError) -> Callable[[], None]:
    """``name`` at ``filename`` does the lazy load: it calls Django's descriptor, which alerts."""
    alert = _function_at(
        f"{SITE_PACKAGES}/zeal/listeners.py",
        "_alert",
        partial(n_plus_one.log_n_plus_one, exception=error),
    )
    descriptor = _function_at(
        f"{SITE_PACKAGES}/django/db/models/fields/related_descriptors.py", "__get__", alert
    )
    return _function_at(filename, name, descriptor)


def test_logs_each_distinct_n_plus_one_once_with_its_line(caplog: pytest.LogCaptureFixture) -> None:
    error = NPlusOneError("N+1 detected on profiles.Profile.owner")
    resolve_owner = _lazy_load_at(RESOLVER, "resolve_owner", error)
    count_owners = _lazy_load_at(SERVICE, "count_owners", error)

    with caplog.at_level(logging.WARNING, logger="zeal"), pytest.warns(UserWarning) as warned:
        for _ in range(2):
            resolve_owner()  # same line twice: one log
        count_owners()  # another line: a second log

    messages = [r.getMessage() for r in caplog.records]
    assert messages == [
        f"N+1 detected on profiles.Profile.owner at {RESOLVER}:2 in resolve_owner",
        f"N+1 detected on profiles.Profile.owner at {SERVICE}:2 in count_owners",
    ]
    # Every detection warns (the report lists each test that hits it), placed at the offending line.
    assert [(w.filename, w.lineno) for w in warned] == [(RESOLVER, 2), (RESOLVER, 2), (SERVICE, 2)]
    assert str(warned[0].message) == messages[0]


def test_points_at_the_baseapp_package_not_at_the_library_or_pytest(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """baseapp-backend is installed in site-packages; the line must still land in it."""
    error = NPlusOneError("N+1 detected on users.User.profile")
    resolver = f"{SITE_PACKAGES}/baseapp_auth/graphql/object_types.py"

    resolve_full_name = _lazy_load_at(resolver, "resolve_full_name", error)

    with caplog.at_level(logging.WARNING, logger="zeal"), pytest.warns(UserWarning) as warned:
        resolve_full_name()

    assert (
        caplog.records[0].getMessage()
        == f"N+1 detected on users.User.profile at {resolver}:2 in resolve_full_name"
    )
    assert (warned[0].filename, warned[0].lineno) == (resolver, 2)


def test_skips_the_test_that_triggered_it(caplog: pytest.LogCaptureFixture) -> None:
    """A test calling the resolver: the line is the resolver's, not the test's."""
    error = NPlusOneError("N+1 detected on users.User.profile")
    resolver = _lazy_load_at(RESOLVER, "resolve_full_name", error)
    test = _function_at(f"{REPO}/baseapp_comments/tests/test_graphql.py", "test_list", resolver)

    with caplog.at_level(logging.WARNING, logger="zeal"), pytest.warns(UserWarning):
        test()

    assert caplog.records[0].getMessage().endswith(f"at {RESOLVER}:2 in resolve_full_name")


def test_an_n_plus_one_only_in_test_setup_or_libraries_has_no_line(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A factory saving a wagtail page: wagtail's own N+1, nothing in BaseApp to fix."""
    error = NPlusOneError("N+1 detected on wagtailcore.Page.get()")
    wagtail_save = _lazy_load_at(f"{SITE_PACKAGES}/wagtail/models/pages.py", "save", error)
    factory = _function_at(f"{REPO}/baseapp_wagtail/tests/factories.py", "create", wagtail_save)

    with caplog.at_level(logging.WARNING, logger="zeal"), pytest.warns(UserWarning):
        factory()

    assert caplog.records[0].getMessage() == (
        "N+1 detected on wagtailcore.Page.get() at <tests or third-party>"
    )


@pytest.mark.parametrize(
    ("filename", "ours"),
    [
        (f"{PROJECT}/apps/users/models.py", True),
        (f"{REPO}/baseapp_comments/graphql/object_types.py", True),
        (f"{REPO}/testproject/settings.py", False),
        (f"{REPO}/baseapp_comments/tests/factories.py", False),
        (f"{REPO}/baseapp_core/tests/fixtures.py", False),
        (f"{REPO}/baseapp_wagtail/conftest.py", False),
        (f"{PROJECT}/apps/users/tests/test_users.py", False),
        (f"{PROJECT}/apps/users/tests.py", False),
        (f"{PROJECT}/apps/users/model_tests.py", False),
        (f"{SITE_PACKAGES}/baseapp_core/models.py", True),
        (f"{SITE_PACKAGES}/baseapp/files/graphql/object_types.py", True),
        (f"{SITE_PACKAGES}/django/db/models/fields/related_descriptors.py", False),
        (f"{SITE_PACKAGES}/zeal/listeners.py", False),
        ("/usr/local/lib/python3.12/contextlib.py", False),
        ("/opt/venv/bin/pytest", False),
    ],
)
def test_is_ours(filename: str, ours: bool) -> None:
    assert n_plus_one._is_ours(filename) is ours


def test_skips_its_own_frames() -> None:
    from baseapp_core.n_plus_one import pytest_plugin

    assert n_plus_one._is_ours(n_plus_one.__file__) is False
    assert n_plus_one._is_ours(pytest_plugin.__file__) is False
    assert n_plus_one._is_ours(__file__) is False  # test code, like any other test


def test_zeal_context_wraps_a_task() -> None:
    outer = _nplusone_context.get()  # NPLUSONE_REPORT=1 runs every test inside a zeal context

    n_plus_one.start_zeal_context(task_id="task-1")
    assert _nplusone_context.get() is not outer
    assert _nplusone_context.get().enabled

    n_plus_one.end_zeal_context(task_id="task-1")

    assert _nplusone_context.get() is outer
    assert "task-1" not in n_plus_one._task_tokens.by_task


def test_a_replaced_task_restores_the_outer_context() -> None:
    """Celery runs a task's replacement under the same id; each end closes its own context."""
    outer = _nplusone_context.get()

    n_plus_one.start_zeal_context(task_id="task-r")
    task = _nplusone_context.get()
    n_plus_one.start_zeal_context(task_id="task-r")  # the replacement
    n_plus_one.end_zeal_context(task_id="task-r")
    assert _nplusone_context.get() is task

    n_plus_one.end_zeal_context(task_id="task-r")
    assert _nplusone_context.get() is outer
    assert "task-r" not in n_plus_one._task_tokens.by_task


def test_each_thread_closes_its_own_task_context() -> None:
    """A threaded worker can run two executions of one task id at once (a retry)."""
    first_open, second_open, first_done = threading.Event(), threading.Event(), threading.Event()
    errors: list[ValueError] = []
    restored: list[bool] = []

    def execution(opens: threading.Event, waits_for: threading.Event) -> None:
        outer = _nplusone_context.get()
        n_plus_one.start_zeal_context(task_id="task-t")
        opens.set()
        waits_for.wait(timeout=5)
        try:
            n_plus_one.end_zeal_context(task_id="task-t")
        except ValueError as error:  # a token reset in a thread other than the one that set it
            errors.append(error)
        restored.append(_nplusone_context.get() is outer)

    def first() -> None:
        try:
            execution(first_open, second_open)  # ends while the second is still open
        finally:
            first_done.set()

    def second() -> None:
        first_open.wait(timeout=5)
        execution(second_open, first_done)

    threads = [threading.Thread(target=first), threading.Thread(target=second)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)

    assert errors == []
    assert restored == [True, True]


def test_the_plugin_loads_without_zeal_installed() -> None:
    """A project without the n_plus_one extra can still list the plugin in its conftest.py."""
    code = (
        "import sys; sys.modules['zeal'] = None\n"  # None makes any zeal import fail
        "import baseapp_core.n_plus_one.pytest_plugin\n"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)

    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    ("installed", "enabled"),
    [
        ({"zeal", "baseapp_core.n_plus_one"}, True),
        ({"zeal"}, False),  # zeal installed for another use: no receivers, so no report
        ({"baseapp_core.n_plus_one"}, False),
        (set(), False),
    ],
)
def test_the_plugin_needs_zeal_and_this_app(
    monkeypatch: pytest.MonkeyPatch, installed: set[str], enabled: bool
) -> None:
    from django.apps import apps

    from baseapp_core.n_plus_one import pytest_plugin

    monkeypatch.setattr(apps, "is_installed", lambda name: name in installed)

    assert pytest_plugin._enabled() is enabled


def test_the_plugin_loads_on_a_pytest_without_terminal_reporter() -> None:
    """pytest exports TerminalReporter only from 8.4; the plugin must load on older ones too."""
    code = (
        "import pytest; del pytest.TerminalReporter\nimport baseapp_core.n_plus_one.pytest_plugin\n"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)

    assert result.returncode == 0, result.stderr


def test_ending_a_task_without_a_context_does_nothing() -> None:
    n_plus_one.end_zeal_context(task_id="task-2")  # nothing stored: must not raise


def test_the_app_is_installed_only_with_zeal() -> None:
    """Off by default in tests, on together under NPLUSONE_REPORT=1 (the test settings)."""
    assert ("baseapp_core.n_plus_one" in settings.INSTALLED_APPS) == (
        "zeal" in settings.INSTALLED_APPS
    )


def test_ready_connects_the_receivers(monkeypatch: pytest.MonkeyPatch) -> None:
    """The worker gets the task hooks from ready(): nothing connects at import any more."""
    import baseapp_core.n_plus_one.apps as app_module

    connected = []
    for target in (nplusone_detected, task_prerun, task_postrun):
        monkeypatch.setattr(
            target,
            "connect",
            lambda receiver, dispatch_uid=None, _t=target: connected.append((_t, receiver)),
        )

    app_module.NPlusOneConfig("baseapp_core.n_plus_one", app_module).ready()

    assert connected == [
        (nplusone_detected, n_plus_one.log_n_plus_one),
        (task_prerun, n_plus_one.start_zeal_context),
        (task_postrun, n_plus_one.end_zeal_context),
    ]


class _Writer:
    """Records what write_report sends to pytest's TerminalReporter, without the colors."""

    def __init__(self) -> None:
        self.text = ""

    def section(self, title: str, **markup: bool) -> None:
        self.text += f"== {title} ==\n"

    def write(self, text: str, **markup: bool) -> None:
        self.text += text

    def line(self, text: str, **markup: bool) -> None:
        self.text += f"{text}\n"


def test_a_baseapp_file_under_a_nested_sys_path_entry_is_still_ours(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """pytest's prepend import mode puts package directories on sys.path; the longest entry would
    give ``base/models.py``, which no longer starts with ``baseapp``."""
    monkeypatch.setattr(sys, "path", [*sys.path, f"{REPO}/baseapp_wagtail"])
    filename = f"{REPO}/baseapp_wagtail/base/models.py"

    assert n_plus_one._is_ours(filename) is True
    assert n_plus_one.short_path(filename) == "baseapp_wagtail/base/models.py"


@pytest.mark.parametrize(
    ("filename", "short"),
    [
        (f"{SITE_PACKAGES}/baseapp_core/models.py", "baseapp_core/models.py"),
        (f"{REPO}/baseapp_comments/signals.py", "baseapp_comments/signals.py"),
        (f"{PROJECT}/apps/users/models.py", "apps/users/models.py"),
        ("<unknown>", "<unknown>"),
    ],
)
def test_short_path(filename: str, short: str) -> None:
    assert n_plus_one.short_path(filename) == short


def test_report_collects_hits_per_line_and_tests(monkeypatch: pytest.MonkeyPatch) -> None:
    report = n_plus_one.Report()
    monkeypatch.setattr(n_plus_one, "report", report)
    hot = _lazy_load_at(
        RESOLVER, "resolve_id", NPlusOneError("N+1 detected on baseapp_core.DocumentId.get()")
    )
    rare = _lazy_load_at(SERVICE, "count", NPlusOneError("N+1 detected on users.User.profile"))

    with pytest.warns(UserWarning):
        report.current_test = "test_a"
        for _ in range(3):
            hot()
        report.current_test = "test_b"
        hot()
        rare()

    assert report.rows() == [  # most hits first
        (
            "baseapp_comments/graphql/object_types.py:2 in resolve_id",
            "baseapp_core.DocumentId.get()",
            4,
            2,
        ),
        ("baseapp_comments/services.py:2 in count", "users.User.profile", 1, 1),
    ]


def test_report_prints_one_tagged_line_per_n_plus_one() -> None:
    report = n_plus_one.Report()
    report.add("baseapp_core/models.py:142 in get_or_create_for_object", "DocumentId.get()")
    report.add("baseapp_core/models.py:142 in get_or_create_for_object", "DocumentId.get()")
    report.add("baseapp_auth/x.py:1 in f", "users.User.profile")
    writer = _Writer()

    n_plus_one.write_report(report, writer)

    hot = "baseapp_core/models.py:142 in get_or_create_for_object"
    rare = "baseapp_auth/x.py:1 in f".ljust(len(hot))  # each column is padded
    assert writer.text == (
        "== N+1 report (zeal): 2 distinct ==\n"
        f"[zeal] {hot}  DocumentId.get()    2 hits, 0 tests\n"
        f"[zeal] {rare}  users.User.profile  1 hit, 0 tests\n"
    )
