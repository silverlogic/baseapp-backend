import logging
import os
import re
import subprocess
import tempfile
import typing
from collections.abc import Sequence
from contextlib import contextmanager
from html import escape
from pathlib import Path
from uuid import uuid4

from django.conf import settings
from django.template import Context
from django.template import Template as DjangoBaseTemplate
from django.template.loader import get_template
from pypdf import PdfReader

from .exceptions import (
    BaseAppBackendPDFChromeNotInstalledException,
    BaseAppBackendPDFRenderToPDFException,
)

logger = logging.getLogger(__name__)

DEFAULT_CHROME_BINARY = "google-chrome"
DEFAULT_TIMEOUT = 60
DEFAULT_EXTRA_ARGS: tuple[str, ...] = ()
DEFAULT_NO_SANDBOX = True


class SupportsRender(typing.Protocol):
    """A template from any engine: Django and Jinja2 templates both have `render(context)`."""

    def render(self, context: typing.Any = ...) -> str: ...


def get_chrome_binary() -> str:
    """The Chrome executable to run (`BASEAPP_PDF_CHROME_BINARY`, default `google-chrome`)."""
    return getattr(settings, "BASEAPP_PDF_CHROME_BINARY", DEFAULT_CHROME_BINARY)


def get_timeout() -> float | None:
    """Seconds a Chrome call may take (`BASEAPP_PDF_TIMEOUT`, default 60; `None` waits forever)."""
    return getattr(settings, "BASEAPP_PDF_TIMEOUT", DEFAULT_TIMEOUT)


def get_extra_args() -> tuple[str, ...]:
    """Arguments appended to every render (`BASEAPP_PDF_EXTRA_ARGS`, default none)."""
    return tuple(getattr(settings, "BASEAPP_PDF_EXTRA_ARGS", DEFAULT_EXTRA_ARGS))


def get_no_sandbox() -> bool:
    """Whether Chrome runs with `--no-sandbox` (`BASEAPP_PDF_NO_SANDBOX`, default True)."""
    return bool(getattr(settings, "BASEAPP_PDF_NO_SANDBOX", DEFAULT_NO_SANDBOX))


def ensure_google_chrome_installed() -> None:
    """
    Ensure that the configured Chrome binary (`BASEAPP_PDF_CHROME_BINARY`) is installed.

    Raises:
        BaseAppBackendPDFChromeNotInstalledException: If the binary is not installed.
    """
    binary = get_chrome_binary()
    try:
        process = subprocess.run(
            [binary, "--version"], check=True, capture_output=True, timeout=get_timeout()
        )
        logger.info(f"{binary} is installed: {process.stdout.decode('utf-8')}")
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
        # OSError covers a missing binary (FileNotFoundError) and one that is not
        # executable (PermissionError) alike.
        raise BaseAppBackendPDFChromeNotInstalledException(binary)


def chrome_available() -> bool:
    """Whether the configured Chrome binary can be run, for callers that degrade without it."""
    try:
        ensure_google_chrome_installed()
    except BaseAppBackendPDFChromeNotInstalledException:
        return False
    return True


def ensure_valid_pdf(file_path: Path) -> None:
    """
    Ensure that the pdf is valid.

    Raises:
        FileNotFoundError: If the file does not exist.
        BaseAppBackendPDFRenderToPDFException: If the file is empty.
        BaseAppBackendPDFRenderToPDFException: If the file is rendered with fatal errors.
    """
    if file_path.exists() is False:
        raise FileNotFoundError(f"File not found: {file_path.as_posix()}")
    if os.stat(file_path.as_posix()).st_size <= 0:
        raise BaseAppBackendPDFRenderToPDFException(f"File size is empty: {file_path.as_posix()}")

    reader = PdfReader(file_path.as_posix())
    page = reader.pages[0]
    text = page.extract_text()
    # The google-chrome --render-to-pdf command can have these errors embedding in the pdf text
    # The google-chrome process will not indicate an error, and a pdf will be rendered, so we need to check the pdf text for these errors
    possible_chrome_rendered_pdf_errors = [
        # This occurs when the source is a local html file, but it does not exist
        "ERR_FILE_NOT_FOUND",
        # This occurs when the source is a url, but there was an error resolving the url
        "DNS_PROBE_FINISHED_NXDOMAIN",
    ]
    for possible_error in possible_chrome_rendered_pdf_errors:
        if possible_error in text:
            raise BaseAppBackendPDFRenderToPDFException(text)


def _build_command(
    source: str, output_file_path: Path, user_data_dir: Path, extra_args: Sequence[str] = ()
) -> list[str]:
    command = [get_chrome_binary(), "--headless"]
    if get_no_sandbox():
        command.append("--no-sandbox")
    command += [
        "--run-all-compositor-stages-before-draw",
        "--disable-gpu",
        "--disable-audio-output",
        "--disable-dev-shm-usage",
        "--no-pdf-header-footer",
        "--print-to-pdf-no-header",
        f"--user-data-dir={user_data_dir.as_posix()}",
        f"--print-to-pdf={output_file_path.as_posix()}",
        *get_extra_args(),
        *extra_args,
        source,
    ]
    return command


@contextmanager
def _work_dir() -> typing.Generator[Path, None, None]:
    """
    A private (0700) temporary directory for one render, removed with everything in it.

    Cleanup errors are ignored so that a file Chrome still holds open can't replace the
    exception that explains a failed render.
    """
    with tempfile.TemporaryDirectory(prefix="baseapp_pdf_", ignore_cleanup_errors=True) as path:
        yield Path(path)


def _print_to_pdf(source: str, work_dir: Path, extra_args: Sequence[str] = ()) -> Path:
    """
    Print `source` to a validated PDF inside `work_dir`, which the caller owns and removes.

    Chrome's profile (`--user-data-dir`) and its own scratch files (`scoped_dir*`, created
    under `TMPDIR`) go in `work_dir` too, so a render never touches what another render is
    using, and cleaning up is removing that one directory.
    """
    output_file_path = work_dir / f"{uuid4()}.pdf"
    scratch_dir = work_dir / "tmp"
    scratch_dir.mkdir(exist_ok=True)
    command = _build_command(source, output_file_path, work_dir / "profile", extra_args)
    env = {**os.environ, "TMPDIR": scratch_dir.as_posix()}
    timeout = get_timeout()

    try:
        subprocess.run(command, capture_output=True, check=True, timeout=timeout, env=env)
    except subprocess.CalledProcessError as error:
        # Chrome exits non-zero for anything it could not load — a host that does not
        # resolve, a refused connection, a timeout. Letting CalledProcessError out breaks
        # this function's contract: callers are told to expect the exception below, and
        # whether a given URL makes Chrome exit non-zero or render an error page to a
        # valid PDF depends on the network it runs on.
        stderr = (error.stderr or b"").decode(errors="replace").strip()
        raise BaseAppBackendPDFRenderToPDFException(
            f"{command[0]} failed to render {source}: {stderr}"
        ) from error
    except subprocess.TimeoutExpired as error:
        # `subprocess.run` has already killed Chrome by the time this is raised.
        raise BaseAppBackendPDFRenderToPDFException(
            f"{command[0]} did not render {source} within {timeout} seconds"
        ) from error

    try:
        ensure_valid_pdf(file_path=output_file_path)
    except FileNotFoundError as error:
        # Chrome can also fail by exiting zero and writing nothing at all, which is
        # what an unreachable host looks like on some networks. That is a render
        # failure like any other, so it is reported as one rather than as a missing
        # file the caller never asked about.
        raise BaseAppBackendPDFRenderToPDFException(
            f"{command[0]} produced no PDF for {source}"
        ) from error
    return output_file_path


@contextmanager
def render_to_pdf(
    *args, source: str | Path, extra_args: Sequence[str] = (), **kwargs
) -> typing.Generator[Path, None, None]:
    """
    Render a source to a pdf file.

    Args:
        source: Local html file path or a url string.
        extra_args: Chrome arguments for this render, after `BASEAPP_PDF_EXTRA_ARGS`.

    Returns:
        A path to the rendered pdf temporary file.
        This file will be deleted after the exiting the context.
    """
    ensure_google_chrome_installed()

    if isinstance(source, Path):
        source = source.as_posix()

    with _work_dir() as work_dir:
        yield _print_to_pdf(source, work_dir, extra_args)


_HEAD_OPEN_TAG = re.compile(r"<head(\s[^>]*)?>", re.IGNORECASE)


def _with_base_url(html: str, base_url: str | None) -> str:
    """Put `<base href>` first in `<head>`, so relative URLs resolve against `base_url`."""
    if not base_url:
        return html
    base_tag = f'<base href="{escape(base_url, quote=True)}">'
    match = _HEAD_OPEN_TAG.search(html)
    if match is None:
        return base_tag + html
    return html[: match.end()] + base_tag + html[match.end() :]


@contextmanager
def _render_html(
    html: str, base_url: str | None = None, extra_args: Sequence[str] = ()
) -> typing.Generator[Path, None, None]:
    with _work_dir() as work_dir:
        html_file_path = work_dir / "index.html"
        # The byte order mark makes Chrome read the file as UTF-8 whatever the HTML
        # declares (or fails to), so non-ASCII text survives a document without
        # `<meta charset>`.
        html_file_path.write_text(_with_base_url(html, base_url), encoding="utf-8-sig")
        yield _print_to_pdf(html_file_path.as_posix(), work_dir, extra_args)


def render_html_to_pdf(
    html: str, *, base_url: str | None = None, extra_args: Sequence[str] = ()
) -> bytes:
    """
    Render an HTML string to PDF bytes.

    Args:
        html: The document to print.
        base_url: What relative URLs in `html` (images, stylesheets, fonts) resolve against,
            e.g. `"https://example.com/static/"` or `"file:///app/static/"`. It is inserted
            as the first `<base>` element, so it wins over one already in `html`. Without it
            relative URLs resolve against the private temporary folder the HTML is written
            to, where nothing else exists.
        extra_args: Chrome arguments for this render, after `BASEAPP_PDF_EXTRA_ARGS`.

    Returns:
        The PDF document. Nothing is left on disk.

    Raises:
        BaseAppBackendPDFChromeNotInstalledException: If Chrome is not installed.
        BaseAppBackendPDFRenderToPDFException: If Chrome fails, times out or produces no PDF.
    """
    ensure_google_chrome_installed()
    with _render_html(html, base_url=base_url, extra_args=extra_args) as pdf_file_path:
        return pdf_file_path.read_bytes()


def render_template_to_html(source: str | SupportsRender, context: dict | None = None) -> str:
    """
    Render a template to an HTML string.

    Args:
        source: A template name, looked up in every configured template engine, or a
            template object with `render(context)` from any backend (Django, Jinja2).
        context: The template context.
    """
    if isinstance(source, str):
        source = get_template(source)
    if callable(getattr(source, "render", None)) is False:
        raise TypeError(f"Expected source to be a string or a template. Got {type(source)}.")

    context = context or {}
    # A template built with `django.template.Template` directly, rather than through an
    # engine, takes a `Context` instead of a dict.
    if isinstance(source, DjangoBaseTemplate):
        return source.render(Context(context)).strip()
    return source.render(context).strip()


@contextmanager
def render_template_to_pdf(
    *args,
    source: str | SupportsRender,
    context: dict | None = None,
    base_url: str | None = None,
    extra_args: Sequence[str] = (),
    **kwargs,
) -> typing.Generator[Path, None, None]:
    """
    Render a template to a pdf file.

    Args:
        source: Name of the template, or a template object with `render(context)` from any
            backend (Django, Jinja2).
        context: The template context.
        base_url: See `render_html_to_pdf`.
        extra_args: Chrome arguments for this render, after `BASEAPP_PDF_EXTRA_ARGS`.

    Returns:
        A path to the rendered pdf temporary file.
        This file will be deleted after the exiting the context.
    """
    html = render_template_to_html(source, context)
    ensure_google_chrome_installed()
    with _render_html(html, base_url=base_url, extra_args=extra_args) as pdf_file_path:
        yield pdf_file_path


def render_template_to_pdf_bytes(
    source: str | SupportsRender,
    context: dict | None = None,
    *,
    base_url: str | None = None,
    extra_args: Sequence[str] = (),
) -> bytes:
    """Render a template to PDF bytes. Arguments are as for `render_template_to_pdf`."""
    return render_html_to_pdf(
        render_template_to_html(source, context), base_url=base_url, extra_args=extra_args
    )
