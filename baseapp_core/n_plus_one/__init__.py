"""N+1 reporting in dev with django-zeal.

An opt-in app: a project's dev settings install it next to zeal, and production never loads it::

    INSTALLED_APPS += ["zeal", "baseapp_core.n_plus_one"]
    MIDDLEWARE = ["zeal.middleware.zeal_middleware"] + MIDDLEWARE
    ZEAL_RAISE = False

zeal reports each N+1 as a Python warning, but a dev server on Daphne loses it: Twisted's logger
takes over ``warnings.showwarning``. So this module also logs zeal's ``nplusone_detected`` signal
(connected in ``apps.py``) on the ``zeal`` logger, once per distinct N+1 and process, which reaches
the console in the web and worker processes alike. Each detection is also emitted as a warning from
module ``baseapp_core.n_plus_one``, placed at the offending line, so ``-W error`` can fail a test on
it. In a test run, ``pytest_plugin`` sets ``report``, which collects every detection for the
"N+1 report (zeal)" section printed at the end of the run.

See README.md.
"""

import logging
import os
import sys
import threading
import warnings
from collections import Counter, defaultdict
from contextvars import Token
from dataclasses import dataclass, field
from typing import Any

from django.conf import settings

logger = logging.getLogger("zeal")

_reported: set[str] = set()


class _TaskTokens(threading.local):
    """The zeal contexts open for tasks, per thread, with a stack per task id.

    A stack, because a task that calls self.replace() runs its replacement under the same id. Per
    thread, because a threaded worker can run two executions of one task id at once (a retry), and
    a context var token resets only in the thread that set it.
    """

    def __init__(self) -> None:
        self.by_task: dict[str, list[Token]] = {}


_task_tokens = _TaskTokens()

WARNING_MODULE = "baseapp_core.n_plus_one"
_PACKAGE_DIR = os.path.dirname(__file__)
# Where an N+1 with no frame of ours happened: test setup, or a library (wagtail, Django, ...).
NO_LINE_OF_OURS = "<tests or third-party>"


def _import_paths(filename: str) -> list[str]:
    """``filename`` relative to each ``sys.path`` entry that contains it, longest entry first.

    More than one can match: pytest's default import mode also puts test directories on sys.path,
    so a test helper inside a BaseApp package is reachable as ``helpers.py`` and as
    ``baseapp_wagtail/tests/helpers.py``.
    """
    roots = {os.path.abspath(entry or os.curdir).rstrip(os.sep) for entry in sys.path}
    matches = sorted(
        (root for root in roots if filename.startswith(f"{root}{os.sep}")), key=len, reverse=True
    )
    return [filename[len(root) + 1 :] for root in matches]


def _baseapp_path(filename: str) -> str | None:
    """The module path of a file in a BaseApp package (``baseapp_core/models.py``), if it is one."""
    return next((path for path in _import_paths(filename) if path.startswith("baseapp")), None)


def _project_dir() -> str:
    return f"{str(settings.BASE_DIR).rstrip(os.sep)}{os.sep}"


def _in_project(filename: str) -> bool:
    return filename.startswith(_project_dir()) and "site-packages" not in filename


def _is_test_code(filename: str) -> bool:
    """Tests, fixtures and factories: an N+1 there is the test building data, not one to fix."""
    directory, name = os.path.split(filename)
    return (
        "tests" in directory.split(os.sep)
        or name.startswith("test_")
        or name.endswith("_tests.py")  # pytest.ini collects these too
        or name in ("tests.py", "conftest.py")
    )


def short_path(filename: str) -> str:
    """The path the report prints: without the site-packages or project prefix."""
    if path := _baseapp_path(filename):
        return path
    if _in_project(filename):
        return filename.removeprefix(_project_dir())
    paths = _import_paths(filename)
    return paths[-1] if paths else filename


def _is_ours(filename: str) -> bool:
    """Project code or a BaseApp package, outside tests: code where an N+1 can be fixed.

    zeal skips everything in site-packages, but projects install baseapp-backend non-editable there,
    so for an N+1 inside a BaseApp package zeal's line lands on pytest or the stdlib. A BaseApp
    package is any module under a top-level ``baseapp*`` package, wherever it is imported from:
    site-packages in a project, the repository root in baseapp-backend itself. Test code is skipped,
    so an N+1 a test triggers points at the code under test; one only in test setup or in a
    third-party package has no line of ours.
    """
    if os.path.dirname(filename) == _PACKAGE_DIR:  # this module and the pytest plugin
        return False
    if _is_test_code(filename):
        return False
    return _in_project(filename) or _baseapp_path(filename) is not None


@dataclass
class Report:
    """Every N+1 a test run hits, keyed by (line, model.field), for the end-of-run summary."""

    hits: Counter = field(default_factory=Counter)
    tests: defaultdict = field(default_factory=lambda: defaultdict(set))
    current_test: str | None = None

    def add(self, location: str, detection: str) -> None:
        key = (location, detection)
        self.hits[key] += 1
        if self.current_test is not None:
            self.tests[key].add(self.current_test)

    def rows(self) -> list[tuple[str, str, int, int]]:
        """(location, model.field, hits, tests), most hits first."""
        return [
            (location, detection, hits, len(self.tests[(location, detection)]))
            for (location, detection), hits in self.hits.most_common()
        ]


report: Report | None = None

MAX_LOCATION_WIDTH = 72  # longer locations overflow the column instead of widening every line


def write_report(report: Report, writer: Any) -> None:
    """Print the report through pytest's TerminalReporter: one line per distinct N+1, most hits
    first. Colors go through pytest's writer, so they drop out when output is redirected or with
    --color=no."""
    rows = report.rows()
    writer.section(f"N+1 report (zeal): {len(rows)} distinct", sep="=", yellow=True)
    location_width = min(max((len(row[0]) for row in rows), default=0), MAX_LOCATION_WIDTH)
    detection_width = max((len(row[1]) for row in rows), default=0)
    for location, detection, hits, tests in rows:
        writer.write("[zeal] ", yellow=True, bold=True)
        writer.write(location.ljust(location_width), bold=True)
        writer.write(f"  {detection.ljust(detection_width)}", cyan=True)
        writer.line(f"  {_plural(hits, 'hit')}, {_plural(tests, 'test')}")


def _plural(count: int, noun: str) -> str:
    return f"{count} {noun}{'s' * (count != 1)}"


def _caller() -> tuple[str, int, str] | None:
    """The innermost frame in our code (see _is_ours): the line that did the lazy load."""
    frame = sys._getframe(1)
    while frame is not None:
        if _is_ours(frame.f_code.co_filename):
            return frame.f_code.co_filename, frame.f_lineno, frame.f_code.co_name
        frame = frame.f_back
    return None


def log_n_plus_one(exception: Exception, **kwargs: Any) -> None:
    """Log each distinct N+1 (model, field, line) once per process, and warn at its line.

    The signal carries only "N+1 detected on <model>.<field>"; the line comes from _caller().
    """
    caller = _caller()
    if caller is None:
        filename, lineno = NO_LINE_OF_OURS, 0
        location = short_location = NO_LINE_OF_OURS
    else:
        filename, lineno, function = caller
        location = f"{filename}:{lineno} in {function}"
        short_location = f"{short_path(filename)}:{lineno} in {function}"
    message = f"{exception} at {location}"
    warnings.warn_explicit(
        message, UserWarning, filename=filename, lineno=lineno, module=WARNING_MODULE
    )
    if message not in _reported:
        _reported.add(message)
        logger.warning(message)
    if report is not None:
        detection = str(exception).removeprefix("N+1 detected on ")
        report.add(short_location, detection)


# zeal is imported in the receivers, not at the top: loading pytest_plugin imports this package,
# and a project without the n_plus_one extra must still be able to load it.


def start_zeal_context(task_id: str, **kwargs: Any) -> None:
    """Open a zeal context per task: the middleware covers requests, not tasks the worker runs."""
    from zeal import setup

    _task_tokens.by_task.setdefault(task_id, []).append(setup())


def end_zeal_context(task_id: str, **kwargs: Any) -> None:
    """Close the task's innermost zeal context; task_postrun fires on failure too."""
    from zeal import teardown

    tokens = _task_tokens.by_task.get(task_id)
    if tokens:
        teardown(tokens.pop())
        if not tokens:
            del _task_tokens.by_task[task_id]
