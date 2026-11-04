import subprocess
import time
from pathlib import Path

import pytest

from baseapp_pdf.utils import run_chrome

# `run_chrome` runs any command; these use `sh` so they need no Chrome.


def test_returns_the_output() -> None:
    result = run_chrome(["sh", "-c", "echo out; echo err >&2"], timeout=10)

    assert result.returncode == 0
    assert result.stdout == b"out\n"
    assert result.stderr == b"err\n"


def test_non_zero_exit_raises() -> None:
    with pytest.raises(subprocess.CalledProcessError) as excinfo:
        run_chrome(["sh", "-c", "echo failed >&2; exit 3"], timeout=10)

    assert excinfo.value.returncode == 3
    assert excinfo.value.stderr == b"failed\n"


def test_missing_binary_raises() -> None:
    with pytest.raises(FileNotFoundError):
        run_chrome(["baseapp-pdf-no-such-binary"], timeout=10)


def test_timeout_kills_the_processes_it_started(tmp_path: Path) -> None:
    # Like Chrome's helpers, the background child outlives the main process unless the
    # whole session is killed, and it writes to the directory being cleaned up.
    marker = tmp_path / "written-after-the-timeout"
    started = time.monotonic()

    with pytest.raises(subprocess.TimeoutExpired):
        run_chrome(["sh", "-c", '(sleep 1; touch "$0") & sleep 30', marker.as_posix()], timeout=0.3)

    assert time.monotonic() - started < 5
    time.sleep(1.5)
    assert not marker.exists()
