"""Compile .po catalogs into the .mo files committed next to them.

    python scripts/i18n/compile_catalogs.py path/to/django.po [...]

Run from the repository root by the `compile-translations` pre-commit hook for
every staged .po (`pre-commit run compile-translations --all-files` compiles all
of them). Only catalogs found under the repository root are compiled. A .mo
is rewritten only when its messages or plural rule differ from the .po, so
recompiling never churns the binary. Exits 1 when a .mo was written, so the
commit stops until it is staged too. CI (`check_translations`) fails on any .mo
that does not match its .po.
"""

import gettext
import os
import sys
import tempfile
from pathlib import Path

import polib

SKIP_DIRS = {"node_modules", "__pycache__"}


def repo_catalogs(root: Path) -> dict[str, Path]:
    """Every .po under ``root`` keyed by its POSIX path relative to it, skipping dot dirs."""
    catalogs = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not d.startswith(".") and d not in SKIP_DIRS]
        for name in filenames:
            if name.endswith(".po"):
                path = Path(dirpath, name)
                catalogs[path.relative_to(root).as_posix()] = path
    return catalogs


def compiled_messages(mo_file: Path) -> tuple[dict, str | None]:
    """Messages (header excluded) and the plural rule of a compiled catalog."""
    with mo_file.open("rb") as fp:
        translations = gettext.GNUTranslations(fp)
    messages = {key: value for key, value in translations._catalog.items() if key != ""}
    return messages, translations._info.get("plural-forms")


def compile_catalog(po_file: Path) -> bool:
    """Write ``po_file``'s .mo when it is missing or stale. Returns whether it was written."""
    mo_file = po_file.with_suffix(".mo")
    with tempfile.TemporaryDirectory() as tmp:
        fresh = Path(tmp) / "django.mo"
        polib.pofile(str(po_file)).save_as_mofile(str(fresh))
        if mo_file.exists() and compiled_messages(mo_file) == compiled_messages(fresh):
            return False
        mo_file.write_bytes(fresh.read_bytes())
    return True


def main(paths: list[str]) -> int:
    requested = {Path(path).as_posix() for path in paths}
    catalogs = repo_catalogs(Path.cwd())
    for path in sorted(requested - catalogs.keys()):
        print(f"skipped {path}: not a catalog under {Path.cwd()}")
    written = [
        catalogs[key]
        for key in sorted(catalogs)
        if key in requested and compile_catalog(catalogs[key])
    ]
    for po_file in written:
        print(f"compiled {po_file.with_suffix('.mo')}: stage it with its .po")
    return 1 if written else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
