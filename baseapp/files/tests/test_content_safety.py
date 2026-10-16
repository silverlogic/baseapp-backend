import pytest
from django.test import override_settings

from baseapp.files.content_safety import (
    DEFAULT_ALLOWED_FILE_TYPES,
    allowed_content_type,
    file_extension,
    is_inline_safe,
)


@pytest.mark.parametrize(
    "file_name, content_type",
    [
        ("clip.mp4", "video/mp4"),
        ("PHOTO.JPG", "image/jpeg"),
        ("report.pdf", "application/pdf"),
        ("sheet.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        ("bundle.zip", "application/zip"),
        ("dir/notes.txt", "text/plain"),
        ("page.html.txt", "text/plain"),
        ("page.html", None),
        ("page.html.", None),
        ("page.html ", None),
        ("drawing.svg", None),
        ("feed.xml", None),
        ("app.js", None),
        ("tool.exe", None),
        ("README", None),
        ("", None),
    ],
)
def test_default_allowlist(file_name: str, content_type: str | None) -> None:
    assert allowed_content_type(file_name) == content_type


def test_default_allowlist_has_no_types_browsers_run_as_pages() -> None:
    page_types = {"text/html", "image/svg+xml", "application/xhtml+xml", "text/javascript"}
    assert not page_types & set(DEFAULT_ALLOWED_FILE_TYPES.values())


@override_settings(BASEAPP_FILES_ALLOWED_FILE_TYPES={".PDF": "application/pdf"})
def test_projects_can_replace_the_allowlist_with_a_dict() -> None:
    assert allowed_content_type("report.pdf") == "application/pdf"
    assert allowed_content_type("clip.mp4") is None


@override_settings(BASEAPP_FILES_ALLOWED_FILE_TYPES=[".png", ".weird"])
def test_a_list_of_extensions_takes_types_from_mimetypes() -> None:
    assert allowed_content_type("photo.png") == "image/png"
    assert allowed_content_type("data.weird") == "application/octet-stream"
    assert allowed_content_type("clip.mp4") is None


@override_settings(
    BASEAPP_FILES_ALLOWED_FILE_TYPES={**DEFAULT_ALLOWED_FILE_TYPES, ".svg": "image/svg+xml"}
)
def test_projects_can_extend_the_default() -> None:
    assert allowed_content_type("drawing.svg") == "image/svg+xml"
    assert allowed_content_type("clip.mp4") == "video/mp4"


@pytest.mark.parametrize(
    "content_type, inline",
    [
        ("image/jpeg", True),
        ("video/webm", True),
        ("audio/mpeg", True),
        ("application/pdf; charset=binary", True),
        ("image/svg+xml", False),
        ("text/plain", False),
        ("application/zip", False),
        ("", False),
    ],
)
def test_inline_safe_types(content_type: str, inline: bool) -> None:
    assert is_inline_safe(content_type) is inline


def test_file_extension_uses_the_base_name() -> None:
    assert file_extension("dir.html/report") == ""
