import logging
import os
import re
import shutil
import signal
import subprocess
import tempfile
import time
import typing
from collections.abc import Sequence
from contextlib import contextmanager
from html import escape
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
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
DEFAULT_RESTRICTED = False


class SupportsRender(typing.Protocol):
    """A template from any engine: Django and Jinja2 templates both have `render(context)`."""

    def render(self, context: typing.Any = ...) -> str:
        """Render the template with `context`."""


def get_chrome_binary() -> str:
    """The Chrome executable to run (`BASEAPP_PDF_CHROME_BINARY`, default `google-chrome`)."""
    return getattr(settings, "BASEAPP_PDF_CHROME_BINARY", DEFAULT_CHROME_BINARY)


def get_timeout() -> float | None:
    """Seconds a Chrome call may take (`BASEAPP_PDF_TIMEOUT`, default 60; `None` waits forever)."""
    return getattr(settings, "BASEAPP_PDF_TIMEOUT", DEFAULT_TIMEOUT)


def get_extra_args() -> tuple[str, ...]:
    """Arguments appended to every render (`BASEAPP_PDF_EXTRA_ARGS`, default none)."""
    extra_args = getattr(settings, "BASEAPP_PDF_EXTRA_ARGS", DEFAULT_EXTRA_ARGS)
    if isinstance(extra_args, str):
        raise ImproperlyConfigured(_extra_args_error("BASEAPP_PDF_EXTRA_ARGS", extra_args))
    return tuple(extra_args)


def _extra_args_error(name: str, value: str) -> str:
    # A string would otherwise be split into one Chrome argument per character.
    return f"{name} must be a list of arguments, not a string. Use [{value!r}]."


def get_no_sandbox() -> bool:
    """Whether Chrome runs with `--no-sandbox` (`BASEAPP_PDF_NO_SANDBOX`, default True)."""
    return bool(getattr(settings, "BASEAPP_PDF_NO_SANDBOX", DEFAULT_NO_SANDBOX))


def run_chrome(
    command: Sequence[str], *, timeout: float | None, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess:
    """
    Run a Chrome command, like `subprocess.run(command, capture_output=True, check=True)`.

    Chrome runs in a session of its own, and if it is still running when `timeout` expires
    (or the wait is interrupted) the whole session is killed. `subprocess.run` kills only
    the main process, and Chrome's helper processes (renderer, network service) then go on
    running, and writing to the profile while it is being removed.

    Every Chrome call in this package goes through here, so tests patch
    `baseapp_pdf.utils.run_chrome` rather than `subprocess.run` for the whole process.

    Raises:
        OSError: If the binary can't be run.
        subprocess.CalledProcessError: If Chrome exits non-zero.
        subprocess.TimeoutExpired: If Chrome takes longer than `timeout` seconds.
    """
    with subprocess.Popen(
        list(command),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        start_new_session=True,
    ) as process:
        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except BaseException:
            _kill_session(process)
            raise
    if process.returncode:
        raise subprocess.CalledProcessError(process.returncode, process.args, stdout, stderr)
    return subprocess.CompletedProcess(process.args, process.returncode, stdout, stderr)


def _kill_session(process: subprocess.Popen) -> None:
    """Kill `process` and every process it started; the caller then waits for it."""
    if not hasattr(os, "killpg"):  # pragma: no cover - Windows has no process groups
        process.kill()
        return
    try:
        # The process has not been waited for yet, so its id still names its group.
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:  # pragma: no cover - the group has already exited
        pass


def get_restricted() -> bool:
    """Whether HTML renders are restricted by default (`BASEAPP_PDF_RESTRICTED`, default False)."""
    return bool(getattr(settings, "BASEAPP_PDF_RESTRICTED", DEFAULT_RESTRICTED))


def ensure_google_chrome_installed() -> None:
    """
    Ensure that the configured Chrome binary (`BASEAPP_PDF_CHROME_BINARY`) is installed.

    Raises:
        BaseAppBackendPDFChromeNotInstalledException: If the binary is not installed.
    """
    binary = get_chrome_binary()
    try:
        process = run_chrome([binary, "--version"], timeout=get_timeout())
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
    if isinstance(extra_args, str):
        raise TypeError(_extra_args_error("extra_args", extra_args))
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
    """A private (0700) temporary directory for one render, removed with everything in it."""
    path = Path(tempfile.mkdtemp(prefix="baseapp_pdf_"))
    try:
        yield path
    finally:
        _remove_work_dir(path)


def _remove_work_dir(path: Path, attempts: int = 3, delay: float = 0.2) -> None:
    """
    Remove `path`, retrying while a Chrome process that was just killed still writes to it.

    It never raises, so that a cleanup failure can't replace the exception that explains a
    failed render; a directory that can't be removed is logged instead.
    """
    for attempt in range(1, attempts + 1):
        try:
            shutil.rmtree(path)
            return
        except FileNotFoundError:
            return
        except OSError as error:
            if attempt == attempts:
                logger.warning("Could not remove the PDF render directory %s: %s", path, error)
                return
            time.sleep(delay)


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
        run_chrome(command, timeout=timeout, env=env)
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
        # `run_chrome` has already killed Chrome and its helpers by the time this is raised.
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


# What may come before the first element of a document without changing how it is parsed:
# a byte order mark, whitespace, comments (including the `<!-->` and `<!--->` forms, which
# end at once), the doctype and other `<!...>` / `<?...>` bogus comments.
_DOCUMENT_PROLOGUE = re.compile(
    r"\ufeff?(?:[\t\n\f\r ]|<!--(?:-?>|.*?--!?>)|<!(?!--)[^>]*>|<\?[^>]*>)*", re.DOTALL
)


def _insert_in_head(html: str, markup: str) -> str:
    """
    Insert `markup` so that it is the first thing in the document's `<head>`.

    It goes after the prologue and before everything else, `<html>` and `<head>` included:
    anything before the doctype would put the page in quirks mode. The HTML parser opens
    `<html>` and `<head>` itself for an element found there, merges the attributes of the
    document's own `<html>` tag into it and ignores its `<head>` tag, so the result is the
    same as inserting inside `<head>`, without having to find that tag in the text, where it
    can also appear in a comment or a script.
    """
    end = _DOCUMENT_PROLOGUE.match(html).end()
    return html[:end] + markup + html[end:]


_HTTP_EQUIV = re.compile("http-equiv", re.IGNORECASE)
_HOST = re.compile(r"[A-Za-z0-9.:-]+")


def _restricted_origin(base_url: str | None) -> str:
    """The origin a restricted render may load from: `base_url`'s, which must be http(s)."""
    if not base_url:
        return ""
    parts = urlsplit(base_url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        # A `file:` source would open every file on the machine, not only those under
        # `base_url`: a Content-Security-Policy can't limit a file URL to a folder.
        raise ValueError(
            f"A restricted render can only load from an http(s) base_url, not {base_url!r}. "
            "Serve the assets over http(s) or inline them as data: URLs."
        )
    host = parts.hostname
    if not _HOST.fullmatch(host):
        raise ValueError(f"Invalid base_url host: {host!r}")
    if ":" in host:
        host = f"[{host}]"
    port = f":{parts.port}" if parts.port else ""
    return f"{parts.scheme}://{host}{port}"


def _content_security_policy(base_url: str | None) -> str:
    """
    A policy that lets the document load nothing but inline styles, `data:` URLs and
    `base_url`'s origin: no scripts, frames, objects, local files or other hosts.
    """
    origin = _restricted_origin(base_url)
    sources = " ".join(filter(None, ["data:", origin]))
    return (
        f"default-src 'none'; style-src 'unsafe-inline' {sources}; img-src {sources}; "
        f"font-src {sources}; form-action 'none'"
    )


def _prepare_html(html: str, base_url: str | None, restricted: bool) -> str:
    """
    Put `<base href>` first in `<head>`, so relative URLs resolve against `base_url`, and,
    for a restricted render, a Content-Security-Policy before it.
    """
    head = ""
    if restricted:
        # The policy can't stop a `<meta http-equiv="refresh">` from navigating to a local
        # file or another host, so the document's own `http-equiv` attributes are renamed,
        # which makes the browser ignore them. The policy goes in after that, and before
        # anything of the document, so it applies to all of it.
        html = _HTTP_EQUIV.sub("data-blocked-http-equiv", html)
        policy = escape(_content_security_policy(base_url), quote=True)
        head += f'<meta http-equiv="Content-Security-Policy" content="{policy}">'
    if base_url:
        head += f'<base href="{escape(base_url, quote=True)}">'
    return _insert_in_head(html, head) if head else html


@contextmanager
def _render_html(
    html: str,
    base_url: str | None = None,
    extra_args: Sequence[str] = (),
    restricted: bool | None = None,
) -> typing.Generator[Path, None, None]:
    if restricted is None:
        restricted = get_restricted()
    html = _prepare_html(html, base_url, restricted)
    with _work_dir() as work_dir:
        html_file_path = work_dir / "index.html"
        # The byte order mark makes Chrome read the file as UTF-8 whatever the HTML
        # declares (or fails to), so non-ASCII text survives a document without
        # `<meta charset>`.
        html_file_path.write_text(html, encoding="utf-8-sig")
        yield _print_to_pdf(html_file_path.as_posix(), work_dir, extra_args)


def render_html_to_pdf(
    html: str,
    *,
    base_url: str | None = None,
    extra_args: Sequence[str] = (),
    restricted: bool | None = None,
) -> bytes:
    """
    Render an HTML string to PDF bytes.

    The HTML is printed by Chrome from a local file, with network access, so it can show any
    file the process can read (in an `<iframe>`, for example) and request any URL it can
    reach. Only render HTML that is trusted, or sanitised, or pass `restricted=True`. See
    "Security" in the README.

    Args:
        html: The document to print.
        base_url: What relative URLs in `html` (images, stylesheets, fonts) resolve against,
            e.g. `"https://example.com/static/"` or `"file:///app/static/"`. It is inserted
            as the first `<base>` element, so it wins over one already in `html`. Without it
            relative URLs resolve against the private temporary folder the HTML is written
            to, where nothing else exists.
        extra_args: Chrome arguments for this render, after `BASEAPP_PDF_EXTRA_ARGS`.
        restricted: Load nothing but inline styles, `data:` URLs and `base_url`'s origin,
            which must then be http(s), and run no scripts. Defaults to
            `BASEAPP_PDF_RESTRICTED`.

    Returns:
        The PDF document. Nothing is left on disk.

    Raises:
        BaseAppBackendPDFChromeNotInstalledException: If Chrome is not installed.
        BaseAppBackendPDFRenderToPDFException: If Chrome fails, times out or produces no PDF.
        ValueError: If a restricted render is given a `base_url` that isn't http(s).
    """
    ensure_google_chrome_installed()
    with _render_html(
        html, base_url=base_url, extra_args=extra_args, restricted=restricted
    ) as pdf_file_path:
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
    restricted: bool | None = None,
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
        restricted: See `render_html_to_pdf`.

    Returns:
        A path to the rendered pdf temporary file.
        This file will be deleted after the exiting the context.
    """
    html = render_template_to_html(source, context)
    ensure_google_chrome_installed()
    with _render_html(
        html, base_url=base_url, extra_args=extra_args, restricted=restricted
    ) as pdf_file_path:
        yield pdf_file_path


def render_template_to_pdf_bytes(
    source: str | SupportsRender,
    context: dict | None = None,
    *,
    base_url: str | None = None,
    extra_args: Sequence[str] = (),
    restricted: bool | None = None,
) -> bytes:
    """Render a template to PDF bytes. Arguments are as for `render_template_to_pdf`."""
    return render_html_to_pdf(
        render_template_to_html(source, context),
        base_url=base_url,
        extra_args=extra_args,
        restricted=restricted,
    )
