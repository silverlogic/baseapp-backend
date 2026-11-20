import logging
import stat
import subprocess
import typing
from pathlib import Path
from unittest import mock

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.template import Template, engines
from django.test import override_settings

from baseapp_pdf import utils
from baseapp_pdf.exceptions import (
    BaseAppBackendPDFChromeNotInstalledException,
    BaseAppBackendPDFRenderToPDFException,
)
from baseapp_pdf.tests.helpers import FakeChrome, option
from baseapp_pdf.utils import (
    chrome_available,
    ensure_google_chrome_installed,
    render_html_to_pdf,
    render_template_to_html,
    render_template_to_pdf,
    render_template_to_pdf_bytes,
    render_to_pdf,
)


@pytest.fixture
def fake_chrome() -> typing.Generator[FakeChrome, None, None]:
    chrome = FakeChrome()
    with mock.patch("baseapp_pdf.utils.run_chrome", side_effect=chrome):
        yield chrome


def fail_with(error: Exception) -> FakeChrome:
    """A FakeChrome whose renders raise `error`; its `--version` check still passes."""

    class FailingChrome(FakeChrome):
        def __call__(self, command: list[str], *args, **kwargs) -> subprocess.CompletedProcess:
            if "--version" in command:
                return super().__call__(command, *args, **kwargs)
            raise error

    return FailingChrome()


class TestSettings:
    def test_defaults_keep_the_existing_command(self, fake_chrome) -> None:
        render_html_to_pdf("<p>hi</p>")

        version, render = fake_chrome.calls
        assert version["command"] == ["google-chrome", "--version"]
        command = render["command"]
        assert command[:3] == ["google-chrome", "--headless", "--no-sandbox"]
        assert "--print-to-pdf-no-header" in command
        assert render["kwargs"]["timeout"] == 60

    @override_settings(BASEAPP_PDF_CHROME_BINARY="chromium")
    def test_chrome_binary(self, fake_chrome) -> None:
        render_html_to_pdf("<p>hi</p>")

        assert [call["command"][0] for call in fake_chrome.calls] == ["chromium", "chromium"]

    @override_settings(BASEAPP_PDF_TIMEOUT=5)
    def test_timeout_is_passed_to_every_call(self, fake_chrome) -> None:
        render_html_to_pdf("<p>hi</p>")

        assert [call["kwargs"]["timeout"] for call in fake_chrome.calls] == [5, 5]

    @override_settings(BASEAPP_PDF_TIMEOUT=5)
    def test_timeout_raises_a_render_error(self) -> None:
        error = subprocess.TimeoutExpired(cmd=["google-chrome"], timeout=5)
        with mock.patch("baseapp_pdf.utils.run_chrome", side_effect=fail_with(error)):
            with pytest.raises(BaseAppBackendPDFRenderToPDFException) as excinfo:
                render_html_to_pdf("<p>hi</p>")

        assert "within 5 seconds" in str(excinfo.value)
        assert excinfo.value.__cause__ is error

    @override_settings(BASEAPP_PDF_NO_SANDBOX=False)
    def test_sandbox_can_be_kept(self, fake_chrome) -> None:
        render_html_to_pdf("<p>hi</p>")

        assert "--no-sandbox" not in fake_chrome.renders[0]["command"]

    @override_settings(BASEAPP_PDF_EXTRA_ARGS=["--font-render-hinting=none"])
    def test_extra_args_from_settings_then_call_then_source(self, fake_chrome) -> None:
        render_html_to_pdf("<p>hi</p>", extra_args=["--lang=fr"])

        command = fake_chrome.renders[0]["command"]
        assert command[-3:-1] == ["--font-render-hinting=none", "--lang=fr"]
        assert command[-1].endswith("index.html")

    @override_settings(BASEAPP_PDF_EXTRA_ARGS="--lang=fr")
    def test_extra_args_setting_must_not_be_a_string(self, fake_chrome) -> None:
        # A string would be split into one Chrome argument per character.
        with pytest.raises(ImproperlyConfigured, match=r"Use \['--lang=fr'\]"):
            render_html_to_pdf("<p>hi</p>")

        assert fake_chrome.renders == []

    def test_extra_args_must_not_be_a_string(self, fake_chrome) -> None:
        with pytest.raises(TypeError, match=r"Use \['--lang=fr'\]"):
            render_html_to_pdf("<p>hi</p>", extra_args="--lang=fr")

        assert fake_chrome.renders == []

    def test_render_to_pdf_extra_args(self, fake_chrome) -> None:
        with render_to_pdf(source="https://example.com", extra_args=["--lang=fr"]):
            pass

        assert fake_chrome.renders[0]["command"][-2:] == ["--lang=fr", "https://example.com"]


class TestChromeInstalled:
    @pytest.mark.parametrize(
        "error",
        [
            FileNotFoundError(),
            PermissionError(),
            subprocess.CalledProcessError(returncode=1, cmd=["chromium"]),
            subprocess.TimeoutExpired(cmd=["chromium"], timeout=60),
        ],
    )
    @override_settings(BASEAPP_PDF_CHROME_BINARY="chromium")
    def test_not_installed(self, error: Exception) -> None:
        with mock.patch("baseapp_pdf.utils.run_chrome", side_effect=error):
            with pytest.raises(BaseAppBackendPDFChromeNotInstalledException) as excinfo:
                ensure_google_chrome_installed()
            assert chrome_available() is False

        assert str(excinfo.value) == "chromium is not installed"

    def test_installed(self, fake_chrome) -> None:
        assert chrome_available() is True

    def test_exception_default_message_is_unchanged(self) -> None:
        assert (
            str(BaseAppBackendPDFChromeNotInstalledException()) == "google-chrome is not installed"
        )

    def test_nothing_is_rendered_without_chrome(self) -> None:
        with mock.patch("baseapp_pdf.utils.run_chrome", side_effect=FileNotFoundError()):
            with pytest.raises(BaseAppBackendPDFChromeNotInstalledException):
                render_html_to_pdf("<p>hi</p>")


class TestRenderFailures:
    def test_chrome_failure_is_wrapped(self) -> None:
        # Whether an unreachable URL makes Chrome exit non-zero or render an error page
        # depends on the network the suite runs on, so the failing branch is driven
        # directly rather than through DNS.
        error = subprocess.CalledProcessError(
            returncode=1, cmd=["google-chrome"], stderr=b"net::ERR_NAME_NOT_RESOLVED"
        )
        with mock.patch("baseapp_pdf.utils.run_chrome", side_effect=fail_with(error)):
            with pytest.raises(BaseAppBackendPDFRenderToPDFException) as excinfo:
                with render_to_pdf(source="https://not.a.url"):
                    pass

        assert "ERR_NAME_NOT_RESOLVED" in str(excinfo.value)
        assert isinstance(excinfo.value.__cause__, subprocess.CalledProcessError)

    def test_chrome_producing_no_file(self) -> None:
        # The other way Chrome fails: it exits zero and writes nothing. Cleanup must not
        # turn that into a missing-file error of its own, which would replace the
        # exception that explains what went wrong.
        chrome = FakeChrome(write_pdf=False)
        with mock.patch("baseapp_pdf.utils.run_chrome", side_effect=chrome):
            with pytest.raises(BaseAppBackendPDFRenderToPDFException) as excinfo:
                with render_to_pdf(source="https://not.a.url"):
                    pass

        assert "produced no PDF" in str(excinfo.value)
        assert isinstance(excinfo.value.__cause__, FileNotFoundError)

    def test_chrome_error_page_is_a_render_error(self) -> None:
        with mock.patch("baseapp_pdf.utils.run_chrome", side_effect=FakeChrome()):
            with mock.patch("baseapp_pdf.utils.PdfReader") as reader:
                page = reader.return_value.pages.__getitem__.return_value
                page.extract_text.return_value = "DNS_PROBE_FINISHED_NXDOMAIN"
                with pytest.raises(BaseAppBackendPDFRenderToPDFException):
                    render_html_to_pdf("<p>hi</p>")


class TestIsolation:
    def test_each_render_uses_a_private_directory_that_is_removed(self, fake_chrome) -> None:
        with render_to_pdf(source="https://example.com") as pdf_file_path:
            render = fake_chrome.renders[0]
            work_dir = pdf_file_path.parent
            assert stat.S_IMODE(work_dir.stat().st_mode) == 0o700
            assert Path(option(render["command"], "user-data-dir")).parent == work_dir
            assert Path(render["kwargs"]["env"]["TMPDIR"]).parent == work_dir
            assert render["scoped_dir"].exists()

        assert not work_dir.exists()

    def test_concurrent_renders_do_not_delete_each_others_files(self, fake_chrome) -> None:
        # Before each render got its own directory, finishing one render removed every
        # `scoped_dir*` in the shared temp folder, including the ones a render still in
        # progress was using.
        with render_to_pdf(source="https://example.com/a") as first_pdf:
            with render_to_pdf(source="https://example.com/b") as second_pdf:
                assert first_pdf.parent != second_pdf.parent
            first, second = fake_chrome.renders

            assert not second_pdf.exists()
            assert not second["scoped_dir"].exists()
            assert first_pdf.read_bytes().startswith(b"%PDF")
            assert (first["scoped_dir"] / "SingletonCookie").read_text() == "in use"

    def test_render_html_to_pdf_leaves_nothing_on_disk(self, fake_chrome) -> None:
        render_html_to_pdf("<p>hi</p>")

        render = fake_chrome.renders[0]
        assert not Path(render["command"][-1]).exists()
        assert not render["scoped_dir"].exists()


class TestCleanup:
    def test_removal_is_retried_while_chrome_still_writes(self, tmp_path: Path) -> None:
        # A Chrome helper that was just killed can still be writing to the profile, and
        # make the first removal fail.
        with mock.patch.object(utils.shutil, "rmtree", side_effect=[OSError("busy"), None]) as rm:
            with mock.patch.object(utils.time, "sleep") as sleep:
                utils._remove_work_dir(tmp_path)

        assert rm.call_count == 2
        sleep.assert_called_once()

    def test_a_directory_that_cant_be_removed_is_logged(self, tmp_path: Path, caplog) -> None:
        with mock.patch.object(utils.shutil, "rmtree", side_effect=OSError("busy")) as rm:
            with mock.patch.object(utils.time, "sleep"):
                with caplog.at_level(logging.WARNING, logger="baseapp_pdf.utils"):
                    utils._remove_work_dir(tmp_path)

        assert rm.call_count == 3
        assert f"Could not remove the PDF render directory {tmp_path}: busy" in caplog.text

    def test_a_directory_already_gone_is_fine(self, tmp_path: Path, caplog) -> None:
        utils._remove_work_dir(tmp_path / "missing")

        assert caplog.text == ""

    def test_a_cleanup_failure_does_not_hide_the_render_error(self) -> None:
        error = subprocess.TimeoutExpired(cmd=["google-chrome"], timeout=60)
        with mock.patch("baseapp_pdf.utils.run_chrome", side_effect=fail_with(error)):
            with mock.patch.object(utils.shutil, "rmtree", side_effect=OSError("busy")):
                with mock.patch.object(utils.time, "sleep"):
                    with pytest.raises(BaseAppBackendPDFRenderToPDFException):
                        render_html_to_pdf("<p>hi</p>")


class TestRenderHtmlToPdf:
    def test_returns_the_pdf_bytes(self, fake_chrome) -> None:
        pdf = render_html_to_pdf("<p>Café</p>")

        assert pdf.startswith(b"%PDF")
        # Written as UTF-8 with a byte order mark, so Chrome never guesses the encoding.
        assert fake_chrome.renders[0]["html"] == "﻿<p>Café</p>".encode("utf-8")

    @pytest.mark.parametrize(
        "html, expected",
        [
            (
                "<html><head><title>T</title></head><body></body></html>",
                '<base href="https://cdn.example.com/a/"><html><head><title>T</title></head>'
                "<body></body></html>",
            ),
            (
                '<HTML><HEAD lang="en"><base href="/old/"></HEAD></HTML>',
                '<base href="https://cdn.example.com/a/"><HTML><HEAD lang="en">'
                '<base href="/old/"></HEAD></HTML>',
            ),
            (
                "<p>no head</p>",
                '<base href="https://cdn.example.com/a/"><p>no head</p>',
            ),
            (
                "<header>not the head</header>",
                '<base href="https://cdn.example.com/a/"><header>not the head</header>',
            ),
            # Anything before the doctype would put the page in quirks mode.
            (
                "<!DOCTYPE html><html><body><p>x</p></body></html>",
                '<!DOCTYPE html><base href="https://cdn.example.com/a/"><html><body><p>x</p>'
                "</body></html>",
            ),
            (
                '\ufeff\n<!-- generated -->\n<!doctype html>\n<html lang="fr"></html>',
                "\ufeff\n<!-- generated -->\n<!doctype html>\n"
                '<base href="https://cdn.example.com/a/"><html lang="fr"></html>',
            ),
            (
                '<?xml version="1.0"?><!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Strict//EN">'
                "<p>x</p>",
                '<?xml version="1.0"?><!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Strict//EN">'
                '<base href="https://cdn.example.com/a/"><p>x</p>',
            ),
            # A `<head>` in a comment or a script is not the document's head.
            (
                "<!-- <head> --><p>x</p><script>'<head>'</script>",
                '<!-- <head> --><base href="https://cdn.example.com/a/"><p>x</p>'
                "<script>'<head>'</script>",
            ),
            # `<!-->` is a whole comment, so what follows it is already the document.
            (
                "<!--><p>x</p>-->",
                '<!--><base href="https://cdn.example.com/a/"><p>x</p>-->',
            ),
            (
                "<!---><p>x</p>-->",
                '<!---><base href="https://cdn.example.com/a/"><p>x</p>-->',
            ),
        ],
    )
    def test_base_url(self, fake_chrome, html: str, expected: str) -> None:
        render_html_to_pdf(html, base_url="https://cdn.example.com/a/")

        assert fake_chrome.renders[0]["html"].decode("utf-8-sig") == expected

    def test_base_url_is_escaped(self, fake_chrome) -> None:
        render_html_to_pdf("<p>x</p>", base_url='https://example.com/"><script>')

        html = fake_chrome.renders[0]["html"].decode("utf-8-sig")
        assert html.startswith('<base href="https://example.com/&quot;&gt;&lt;script&gt;">')


CSP_NONE = (
    '<meta http-equiv="Content-Security-Policy" content="default-src &#x27;none&#x27;; '
    "style-src &#x27;unsafe-inline&#x27; data:; img-src data:; font-src data:; "
    'form-action &#x27;none&#x27;">'
)


class TestRestricted:
    def test_not_restricted_by_default(self, fake_chrome) -> None:
        render_html_to_pdf('<meta http-equiv="refresh" content="0;url=x"><p>hi</p>')

        assert fake_chrome.renders[0]["html"].decode("utf-8-sig") == (
            '<meta http-equiv="refresh" content="0;url=x"><p>hi</p>'
        )

    def test_policy_comes_first(self, fake_chrome) -> None:
        render_html_to_pdf("<!DOCTYPE html><html><body><p>hi</p></body></html>", restricted=True)

        assert fake_chrome.renders[0]["html"].decode("utf-8-sig") == (
            f"<!DOCTYPE html>{CSP_NONE}<html><body><p>hi</p></body></html>"
        )

    def test_http_equiv_is_disabled(self, fake_chrome) -> None:
        # The policy can't stop a refresh from navigating to a local file or another host.
        render_html_to_pdf(
            '<p>x</p><META HTTP-EQUIV="refresh" content="0;url=file:///etc/passwd">',
            restricted=True,
        )

        assert fake_chrome.renders[0]["html"].decode("utf-8-sig") == (
            f'{CSP_NONE}<p>x</p><META data-blocked-http-equiv="refresh" '
            'content="0;url=file:///etc/passwd">'
        )

    @pytest.mark.parametrize(
        "base_url, origin",
        [
            ("https://cdn.example.com/static/", "https://cdn.example.com"),
            ("http://user:secret@Example.com:8080/a/", "http://example.com:8080"),
            ("https://[::1]:8443/", "https://[::1]:8443"),
        ],
    )
    def test_base_url_origin_is_allowed(self, fake_chrome, base_url: str, origin: str) -> None:
        render_html_to_pdf("<p>x</p>", base_url=base_url, restricted=True)

        html = fake_chrome.renders[0]["html"].decode("utf-8-sig")
        assert f"img-src data: {origin}; font-src data: {origin};" in html
        assert html.endswith(f'<base href="{base_url}"><p>x</p>')

    @pytest.mark.parametrize(
        "base_url", ["file:///app/static/", "/static/", "ftp://example.com/", "https://a;b/"]
    )
    def test_other_base_urls_are_refused(self, fake_chrome, base_url: str) -> None:
        with pytest.raises(ValueError):
            render_html_to_pdf("<p>x</p>", base_url=base_url, restricted=True)

        assert fake_chrome.renders == []

    @override_settings(BASEAPP_PDF_RESTRICTED=True)
    def test_setting(self, fake_chrome) -> None:
        render_html_to_pdf("<p>x</p>")
        render_html_to_pdf("<p>x</p>", restricted=False)

        first, second = (render["html"].decode("utf-8-sig") for render in fake_chrome.renders)
        assert first == f"{CSP_NONE}<p>x</p>"
        assert second == "<p>x</p>"

    def test_templates(self, fake_chrome) -> None:
        render_template_to_pdf_bytes(
            Template("<p>{{ name }}</p>"), {"name": "Ada"}, restricted=True
        )
        with render_template_to_pdf(source=Template("<p>x</p>"), restricted=True):
            pass

        assert [render["html"].decode("utf-8-sig") for render in fake_chrome.renders] == [
            f"{CSP_NONE}<p>Ada</p>",
            f"{CSP_NONE}<p>x</p>",
        ]


class TestTemplates:
    def test_django_template_name(self, fake_chrome) -> None:
        with render_template_to_pdf(
            source="pdfs/render-template-to-pdf-example.html",
            context={"pdf_title": "Example PDF"},
        ) as pdf_file_path:
            assert pdf_file_path.read_bytes().startswith(b"%PDF")

        assert b"<title>Example PDF" in fake_chrome.renders[0]["html"]

    def test_django_backend_template(self) -> None:
        template = engines["django"].from_string("<p>{{ name }}</p>")
        assert render_template_to_html(template, {"name": "Ada"}) == "<p>Ada</p>"

    def test_bare_django_template(self) -> None:
        assert render_template_to_html(Template("<p>{{ name }}</p>"), {"name": "Ada"}) == (
            "<p>Ada</p>"
        )

    def test_jinja2_template(self) -> None:
        template = engines["jinja2"].from_string("<p>{{ name|upper }}</p>")
        assert render_template_to_html(template, {"name": "Ada"}) == "<p>ADA</p>"

    def test_any_object_with_render(self) -> None:
        class Template:
            def render(self, context: dict) -> str:
                return f"  <p>{context['name']}</p>\n"

        assert render_template_to_html(Template(), {"name": "Ada"}) == "<p>Ada</p>"

    def test_no_context(self) -> None:
        assert render_template_to_html(Template("<p>{{ name }}</p>")) == "<p></p>"

    def test_not_a_template(self) -> None:
        with pytest.raises(TypeError):
            render_template_to_html(42)

    def test_render_template_to_pdf_with_a_jinja2_template(self, fake_chrome) -> None:
        template = engines["jinja2"].from_string("<head></head><p>{{ name }}</p>")
        with render_template_to_pdf(
            source=template, context={"name": "Ada"}, base_url="file:///static/"
        ):
            pass

        assert fake_chrome.renders[0]["html"].decode("utf-8-sig") == (
            '<base href="file:///static/"><head></head><p>Ada</p>'
        )

    def test_render_template_to_pdf_bytes(self, fake_chrome) -> None:
        pdf = render_template_to_pdf_bytes(
            Template("<p>{{ name }}</p>"), {"name": "Ada"}, extra_args=["--lang=fr"]
        )

        assert pdf.startswith(b"%PDF")
        render = fake_chrome.renders[0]
        assert render["html"].decode("utf-8-sig") == "<p>Ada</p>"
        assert "--lang=fr" in render["command"]
