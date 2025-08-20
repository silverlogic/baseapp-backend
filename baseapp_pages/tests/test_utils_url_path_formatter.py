import pytest

from baseapp_pages.utils.url_path_formatter import URLPathFormatter


@pytest.mark.parametrize(
    "input_path,expected",
    [
        ("/", "/"),
        (" / ", "/"),
        ("test", "/test"),
        ("/test", "/test"),
        ("//test", "/test"),
        ("/test/", "/test"),
        ("//test//foo//bar//", "/test/foo/bar"),
        ("foo/bar", "/foo/bar"),
        ("/foo/bar", "/foo/bar"),
        ("foo/bar/", "/foo/bar"),
        ("foo//bar", "/foo/bar"),
        ("//foo//bar//", "/foo/bar"),
        ("//foo//bar//baz//", "/foo/bar/baz"),
        ("   /foo/bar/   ", "/foo/bar"),
    ],
)
def test_url_path_formatter_valid(input_path, expected):
    assert URLPathFormatter(input_path)() == expected


@pytest.mark.parametrize(
    "bad_path,error_msg",
    [
        ("", "Path cannot be empty."),
        ("   ", "Path cannot be empty."),
    ],
)
def test_url_path_formatter_raises_on_empty(bad_path, error_msg):
    with pytest.raises(ValueError) as exc:
        URLPathFormatter(bad_path)()
    assert error_msg in str(exc.value)


def test_url_path_formatter_invalid_no_leading_slash_after_format():
    f = URLPathFormatter("foo")
    f.path = "foo"  # forcibly break invariant
    with pytest.raises(ValueError):
        f._validate_path()
