"""CI gate for translation catalogs: freshness and completeness.

* **Freshness** — re-runs ``makemessages`` for the configured locales and fails if
  that changes anything in the catalogs other than the ``POT-Creation-Date`` header
  (i.e. someone added or changed a translatable string without regenerating).
* **Completeness** — every ``.po`` under the checked locale directories must have
  zero untranslated and zero fuzzy entries (``msgfmt --statistics``).

Locale directories default to ``settings.LOCALE_PATHS``; pass ``--locale-dir`` to
check others (e.g. a package's ``locale/``). Locales default to every entry of
``settings.LANGUAGES`` except ``LANGUAGE_CODE``.
"""

import difflib
import os
import re
import subprocess
from pathlib import Path
from typing import Any

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.utils.translation import to_locale

# msgfmt omits zero-valued categories ("1 untranslated message."), so each one is matched on its own.
STATS_PATTERNS = {
    "translated": re.compile(r"(\d+) translated"),
    "fuzzy": re.compile(r"(\d+) fuzzy"),
    "untranslated": re.compile(r"(\d+) untranslated"),
}
POT_DATE_RE = re.compile(r'^"POT-Creation-Date: .*\\n"$', re.M)


def default_locales() -> list[str]:
    base = settings.LANGUAGE_CODE.split("-")[0]
    return [
        to_locale(code)
        for code, _name in settings.LANGUAGES
        if code != settings.LANGUAGE_CODE and code.split("-")[0] != base
    ]


def catalog_statistics(po_file: Path) -> dict[str, int]:
    """Return translated / fuzzy / untranslated counts for ``po_file``."""
    # parse_statistics only understands msgfmt's English wording.
    env = {**os.environ, "LC_ALL": "C", "LANGUAGE": ""}
    result = subprocess.run(
        ["msgfmt", "--statistics", "-o", os.devnull, str(po_file)],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    if result.returncode != 0:
        raise CommandError(f"msgfmt failed for {po_file}:\n{result.stderr}")
    return parse_statistics(result.stderr)


def parse_statistics(text: str) -> dict[str, int]:
    """Parse ``msgfmt --statistics`` output into translated / fuzzy / untranslated counts."""
    stats = {}
    for key, pattern in STATS_PATTERNS.items():
        match = pattern.search(text)
        stats[key] = int(match.group(1)) if match else 0
    return stats


def normalized_catalog(po_file: Path) -> str:
    """Catalog text with gettext's line wrapping undone and the POT-Creation-Date blanked.

    Editors (Rosetta, polib, hand edits) wrap long entries differently from msgmerge;
    the freshness check must only see real content changes.
    """
    result = subprocess.run(
        ["msgcat", "--no-wrap", str(po_file)], capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        raise CommandError(f"msgcat failed for {po_file}:\n{result.stderr}")
    return POT_DATE_RE.sub("", result.stdout)


def catalog_snapshot(locale_dirs: list[Path]) -> dict[Path, str]:
    """Current (normalized) catalog contents keyed by path."""
    snapshot = {}
    for locale_dir in locale_dirs:
        for po_file in sorted(locale_dir.glob("*/LC_MESSAGES/*.po")):
            snapshot[po_file] = normalized_catalog(po_file)
    return snapshot


def snapshot_diff(before: dict[Path, str], after: dict[Path, str]) -> str:
    chunks = []
    for path in sorted(set(before) | set(after)):
        old, new = before.get(path, ""), after.get(path, "")
        if old == new:
            continue
        label = str(path)
        if path not in before:
            label += " (new file)"
        chunks.append(
            "".join(
                difflib.unified_diff(
                    old.splitlines(keepends=True),
                    new.splitlines(keepends=True),
                    fromfile=f"committed/{label}",
                    tofile=f"makemessages/{label}",
                    n=1,
                )
            )
        )
    return "\n".join(chunks)


class Command(BaseCommand):
    help = "Fail if translation catalogs are stale or have untranslated / fuzzy entries."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--locale-dir",
            action="append",
            dest="locale_dirs",
            default=[],
            help="Locale directory to check (repeatable). Defaults to settings.LOCALE_PATHS.",
        )
        parser.add_argument(
            "--locale",
            "-l",
            action="append",
            default=[],
            help="Locale to regenerate (repeatable). Defaults to settings.LANGUAGES.",
        )
        parser.add_argument(
            "--no-makemessages",
            action="store_true",
            help="Skip the freshness check (only verify completeness).",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        locale_dirs = [Path(p) for p in options["locale_dirs"]] or [
            Path(p) for p in settings.LOCALE_PATHS
        ]
        locales = options["locale"] or default_locales()
        if not locale_dirs:
            raise CommandError("No locale directories to check (set LOCALE_PATHS or --locale-dir).")

        failures: list[str] = []

        if not options["no_makemessages"]:
            before = catalog_snapshot(locale_dirs)
            call_command("makemessages", locale=locales, verbosity=0)
            changes = snapshot_diff(before, catalog_snapshot(locale_dirs))
            if changes:
                failures.append(
                    "Catalogs are stale: `makemessages` changed them. Run\n"
                    f"  python manage.py makemessages {' '.join(f'-l {loc}' for loc in locales)}\n"
                    "translate the new entries, and commit the result.\n" + changes
                )

        for locale_dir in locale_dirs:
            po_files = sorted(locale_dir.glob("*/LC_MESSAGES/*.po"))
            if not po_files:
                failures.append(f"No catalogs found under {locale_dir}")
            for po_file in po_files:
                stats = catalog_statistics(po_file)
                if stats["fuzzy"] or stats["untranslated"]:
                    failures.append(
                        f"{po_file}: {stats['untranslated']} untranslated, "
                        f"{stats['fuzzy']} fuzzy (open it in Rosetta or a .po editor)."
                    )
                elif options["verbosity"] > 0:
                    self.stdout.write(f"{po_file}: {stats['translated']} translated, complete.")

        if failures:
            raise CommandError("\n\n".join(failures))
        self.stdout.write(self.style.SUCCESS("Translation catalogs are fresh and complete."))
