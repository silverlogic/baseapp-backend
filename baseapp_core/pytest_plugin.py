"""Shared pytest behavior for baseapp projects, auto-loaded via the ``pytest11`` entry point.

Projects that enable pytest-xdist run their suite in parallel by default via ``addopts`` in
their pytest config (``pytest.ini`` or ``setup.cfg``, e.g. ``-n 2 --dist loadscope``) so CI and
local match. This plugin keeps a *targeted* single-test run serial — fast feedback and a working
``pdb`` — without anyone having to remember a flag. It never *enables* xdist; if a project has no
``-n`` configured, runs stay serial as before.

A run is treated as targeted when a node id (``path::test``) is passed and no explicit ``-n``
was given; then xdist is disabled for that invocation. Pass ``-n <N>`` explicitly to force
parallel even for a targeted run, or ``-n 0`` to force serial for a full run.
"""

import pytest


@pytest.hookimpl(tryfirst=True)
def pytest_cmdline_main(config) -> None:
    args = config.invocation_params.args
    passed_n = any(a == "-n" or a.startswith(("-n", "--numprocesses")) for a in args)
    if not passed_n and any("::" in a for a in args):
        config.option.numprocesses = 0
        config.option.dist = "no"
