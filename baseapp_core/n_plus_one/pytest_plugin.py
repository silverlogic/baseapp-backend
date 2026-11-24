"""The pytest side of baseapp_core.n_plus_one: a zeal context per test and the end-of-run report.

Load it from the project's root conftest.py (``pytest_plugins = ["baseapp_core.n_plus_one.pytest_plugin"]``)
or with ``-p baseapp_core.n_plus_one.pytest_plugin``. It does nothing unless the test settings
install "zeal" (and this app); zeal is imported only then.
"""

import sys
from collections.abc import Iterator

import pytest
from django.conf import settings


def _enabled() -> bool:
    return "zeal" in settings.INSTALLED_APPS


@pytest.fixture(autouse=True)
def n_plus_one_report(request: pytest.FixtureRequest) -> Iterator[None]:
    """Run each test inside a zeal context and record its N+1s for the end-of-run report."""
    if not _enabled():
        yield
        return

    from zeal import zeal_context

    from baseapp_core import n_plus_one

    if n_plus_one.report is None:
        n_plus_one.report = n_plus_one.Report()
    # A local reference: a test may swap n_plus_one.report (see tests/test_n_plus_one.py).
    report = n_plus_one.report
    report.current_test = request.node.nodeid
    try:
        with zeal_context():
            yield
    finally:
        report.current_test = None


def pytest_terminal_summary(terminalreporter: pytest.TerminalReporter) -> None:
    """Print the "N+1 report (zeal)" section, when the run collected one."""
    # Looked up, not imported: importing it imports zeal, which a project may not install.
    n_plus_one = sys.modules.get("baseapp_core.n_plus_one")
    if n_plus_one is not None and n_plus_one.report is not None:
        n_plus_one.write_report(n_plus_one.report, terminalreporter)
