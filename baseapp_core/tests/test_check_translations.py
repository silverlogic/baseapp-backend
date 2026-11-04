import subprocess
from pathlib import Path

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from baseapp_core.management.commands.check_translations import (
    catalog_statistics,
    compiled_catalog_problem,
    default_locales,
    parse_statistics,
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


def compile_mo(po_file: Path) -> None:
    subprocess.run(["msgfmt", "-o", str(po_file.with_suffix(".mo")), str(po_file)], check=True)


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
    compile_mo(write_catalog(tmp_path, "es", 'msgid "Hello"\nmsgstr "Hola"\n'))
    call_command("check_translations", "--no-makemessages", locale_dirs=[str(tmp_path)])


def test_command_fails_for_incomplete_catalogs(tmp_path) -> None:
    write_catalog(tmp_path, "es", 'msgid "Hello"\nmsgstr ""\n')
    with pytest.raises(CommandError, match="1 untranslated"):
        call_command("check_translations", "--no-makemessages", locale_dirs=[str(tmp_path)])


def test_command_fails_when_the_mo_is_missing(tmp_path) -> None:
    write_catalog(tmp_path, "es", 'msgid "Hello"\nmsgstr "Hola"\n')
    with pytest.raises(CommandError, match="django.mo is missing"):
        call_command("check_translations", "--no-makemessages", locale_dirs=[str(tmp_path)])


def test_compiled_catalog_problem_reports_a_stale_mo(tmp_path) -> None:
    po_file = write_catalog(tmp_path, "es", 'msgid "Hello"\nmsgstr "Hola"\n')
    compile_mo(po_file)
    po_file.write_text(HEADER + '\nmsgid "Hello"\nmsgstr "Buenas"\n', encoding="utf-8")
    assert (
        compiled_catalog_problem(po_file) == f"{po_file.with_suffix('.mo')} does not match its .po"
    )


def test_compiled_catalog_problem_ignores_header_metadata(tmp_path) -> None:
    po_file = write_catalog(tmp_path, "es", 'msgid "Hello"\nmsgstr "Hola"\n')
    compile_mo(po_file)
    po_file.write_text(
        HEADER.replace(
            '"Language: es\\n"\n', '"Language: es\\n"\n"POT-Creation-Date: 2026-10-29\\n"\n'
        )
        + '\nmsgid "Hello"\nmsgstr "Hola"\n',
        encoding="utf-8",
    )
    assert compiled_catalog_problem(po_file) is None


def test_compiled_catalog_problem_reports_a_changed_plural_rule(tmp_path) -> None:
    po_file = write_catalog(tmp_path, "pt", 'msgid "Hello"\nmsgstr "Olá"\n')
    compile_mo(po_file)
    po_file.write_text(
        HEADER.replace("plural=(n != 1)", "plural=(n > 1)") + '\nmsgid "Hello"\nmsgstr "Olá"\n',
        encoding="utf-8",
    )
    assert compiled_catalog_problem(po_file) is not None


def test_command_fails_when_no_catalogs(tmp_path) -> None:
    with pytest.raises(CommandError, match="No catalogs found"):
        call_command("check_translations", "--no-makemessages", locale_dirs=[str(tmp_path)])


@pytest.mark.parametrize(
    "output, expected",
    [
        ("3 translated messages.", {"translated": 3, "fuzzy": 0, "untranslated": 0}),
        ("1 untranslated message.", {"translated": 0, "fuzzy": 0, "untranslated": 1}),
        ("2 fuzzy translations.", {"translated": 0, "fuzzy": 2, "untranslated": 0}),
        (
            "5 translated messages, 2 fuzzy translations, 1 untranslated message.",
            {"translated": 5, "fuzzy": 2, "untranslated": 1},
        ),
        (
            "4 translated messages, 1 untranslated message.",
            {"translated": 4, "fuzzy": 0, "untranslated": 1},
        ),
        ("", {"translated": 0, "fuzzy": 0, "untranslated": 0}),
    ],
)
def test_parse_statistics_handles_every_msgfmt_shape(output, expected) -> None:
    assert parse_statistics(output) == expected


def test_catalog_statistics_counts_an_untranslated_only_catalog(tmp_path) -> None:
    po_file = write_catalog(tmp_path, "es", 'msgid "Missing"\nmsgstr ""\n')
    assert catalog_statistics(po_file) == {"translated": 0, "fuzzy": 0, "untranslated": 1}


def test_catalog_statistics_ignores_the_caller_locale(tmp_path, monkeypatch) -> None:
    po_file = write_catalog(tmp_path, "es", 'msgid "Hello"\nmsgstr ""\n')
    monkeypatch.setenv("LC_ALL", "es_ES.UTF-8")
    monkeypatch.setenv("LANGUAGE", "es")
    assert catalog_statistics(po_file)["untranslated"] == 1
