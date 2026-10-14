import pytest
from django.test import override_settings

from baseapp.files.content_safety import (
    file_extension,
    is_blocked_content_type,
    is_blocked_extension,
    is_inline_safe,
)


@pytest.mark.parametrize(
    "file_name, blocked",
    [
        ("page.html", True),
        ("PAGE.HTM", True),
        ("drawing.svg", True),
        ("feed.xml", True),
        ("app.js", True),
        ("page.html.", True),
        ("page.html ", True),
        ("dir/page.xhtml", True),
        ("dir\\page.svg", True),
        ("clip.mp4", False),
        ("report.pdf", False),
        ("page.html.txt", False),
        ("README", False),
    ],
)
def test_blocked_extensions(file_name: str, blocked: bool) -> None:
    assert is_blocked_extension(file_name) is blocked


@pytest.mark.parametrize(
    "content_type, blocked",
    [
        ("text/html", True),
        ("Text/HTML; charset=utf-8", True),
        ("image/svg+xml", True),
        ("application/atom+xml", True),
        ("application/javascript", True),
        ("video/mp4", False),
        ("application/pdf", False),
        ("application/octet-stream", False),
        ("", False),
    ],
)
def test_blocked_content_types(content_type: str, blocked: bool) -> None:
    assert is_blocked_content_type(content_type) is blocked


@override_settings(
    BASEAPP_FILES_BLOCKED_EXTENSIONS=[".exe"], BASEAPP_FILES_BLOCKED_CONTENT_TYPES=["text/x-sh"]
)
def test_projects_can_replace_the_lists() -> None:
    assert is_blocked_extension("tool.EXE") is True
    assert is_blocked_extension("drawing.svg") is False
    assert is_blocked_content_type("text/x-sh") is True
    assert is_blocked_content_type("image/svg+xml") is False


@pytest.mark.parametrize(
    "content_type, inline",
    [
        ("image/jpeg", True),
        ("video/webm", True),
        ("audio/mpeg", True),
        ("application/pdf; charset=binary", True),
        ("image/svg+xml", False),
        ("text/plain", False),
        ("text/html", False),
        ("", False),
    ],
)
def test_inline_safe_types(content_type: str, inline: bool) -> None:
    assert is_inline_safe(content_type) is inline


def test_file_extension_uses_the_base_name() -> None:
    assert file_extension("dir.html/report") == ""
