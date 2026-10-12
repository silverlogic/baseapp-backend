from pathlib import Path

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from baseapp_core.management.commands.check_translations import (
    catalog_statistics,
    default_locales,
)

HEADER = (
    'msgid ""\n'
    'msgstr ""\n'
    '"Content-Type: text/plain; charset=UTF-8\\n"\n'
    '"Language: es\\n"\n'
    '"Plural-Forms: nplurals=2; plural=(n != 1);\\n"\n'
)


def write_catalog(root: Path, locale: str, body: str) -> Path:
    po_dir = root / locale / "LC_MESSAGES"
    po_dir.mkdir(parents=True)
    po_file = po_dir / "django.po"
    po_file.write_text(HEADER + "\n" + body, encoding="utf-8")
    return po_file


def test_catalog_statistics_counts_fuzzy_and_untranslated(tmp_path) -> None:
    po_file = write_catalog(
        tmp_path,
        "es",
        'msgid "Hello"\nmsgstr "Hola"\n\n'
        '#, fuzzy\nmsgid "Bye"\nmsgstr "Adios"\n\n'
        'msgid "Missing"\nmsgstr ""\n',
    )
    assert catalog_statistics(po_file) == {"translated": 1, "fuzzy": 1, "untranslated": 1}


def test_default_locales_skip_the_source_language(settings) -> None:
    settings.LANGUAGE_CODE = "en-us"
    settings.LANGUAGES = [("en", "English"), ("es", "Spanish"), ("pt-br", "Portuguese")]
    assert default_locales() == ["es", "pt_BR"]


def test_command_passes_for_complete_catalogs(tmp_path) -> None:
    write_catalog(tmp_path, "es", 'msgid "Hello"\nmsgstr "Hola"\n')
    call_command("check_translations", "--no-makemessages", locale_dirs=[str(tmp_path)])


def test_command_fails_for_incomplete_catalogs(tmp_path) -> None:
    write_catalog(tmp_path, "es", 'msgid "Hello"\nmsgstr ""\n')
    with pytest.raises(CommandError, match="1 untranslated"):
        call_command("check_translations", "--no-makemessages", locale_dirs=[str(tmp_path)])


def test_command_fails_when_no_catalogs(tmp_path) -> None:
    with pytest.raises(CommandError, match="No catalogs found"):
        call_command("check_translations", "--no-makemessages", locale_dirs=[str(tmp_path)])
