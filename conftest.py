import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).parent
SKIP_DIRS = {".venv", "node_modules", "site-packages"}


def compile_catalogs(root: Path) -> None:
    """Build the .mo files the translation tests need (most .mo files are not tracked in git)."""
    if shutil.which("msgfmt") is None:
        raise RuntimeError(
            "gettext (msgfmt) is required to run the tests: it compiles the catalogs"
        )
    for po in root.glob("**/locale/*/LC_MESSAGES/*.po"):
        if SKIP_DIRS.intersection(po.parts):
            continue
        mo = po.with_suffix(".mo")
        if mo.exists() and mo.stat().st_mtime >= po.stat().st_mtime:
            continue
        subprocess.run(["msgfmt", "--check-format", "-o", str(mo), str(po)], check=True)


def pytest_configure(config) -> None:
    compile_catalogs(ROOT)
