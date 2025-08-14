import logging
import os
import shutil
import subprocess
import tempfile
import typing
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

from django.template.backends.django import Template as DjangoTemplate
from django.template.loader import get_template
from pypdf import PdfReader

from .exceptions import (
    BaseAppBackendPDFChromeNotInstalledException,
    BaseAppBackendPDFRenderToPDFException,
)

logger = logging.getLogger(__name__)


def ensure_google_chrome_installed() -> None:
    """
    Ensure that google-chrome is installed.

    Raises:
        BaseAppBackendPDFChromeNotInstalledException: If google-chrome is not installed.
    """
    try:
        process = subprocess.run(["google-chrome", "--version"], check=True, capture_output=True)
        logger.info(f"google-chrome is installed: {process.stdout.decode('utf-8')}")
    except (subprocess.CalledProcessError, FileNotFoundError):
        raise BaseAppBackendPDFChromeNotInstalledException()


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


@contextmanager
def render_to_pdf(*args, source: str | Path, **kwargs) -> typing.Generator[Path, None, None]:
    """
    Render a source to a pdf file.

    Args:
        source: Local html file path or a url string.

    Returns:
        A path to the rendered pdf temporary file.
        This file will be deleted after the exiting the context.
    """
    ensure_google_chrome_installed()

    if isinstance(source, Path):
        source = source.as_posix()

    output_file_path = Path(tempfile.gettempdir()).joinpath(f"{uuid4()}.pdf")
    if output_file_path.exists():
        output_file_path.unlink()

    command = [
        "google-chrome",
        "--headless",
        "--no-sandbox",
        "--run-all-compositor-stages-before-draw",
        "--single-process",
        "--disable-gpu",
        "--disable-audio-output",
        "--disable-dev-shm-usage",
        "--no-pdf-header-footer",
        "--print-to-pdf-no-header",
        f"--print-to-pdf={output_file_path.as_posix()}",
        source,
    ]

    process = subprocess.run(
        command,
        capture_output=True,
        check=True,
    )
    process.check_returncode()

    try:
        ensure_valid_pdf(file_path=output_file_path)
        yield output_file_path
    except BaseException as e:
        raise e
    finally:
        output_file_path.unlink()
        # Delete google-chrome generated tmp files
        for file_path in Path(tempfile.gettempdir()).glob("scoped_dir*"):
            if file_path.is_dir():
                shutil.rmtree(file_path)


@contextmanager
def render_template_to_pdf(
    *args, source: str | DjangoTemplate, context: dict = {}, **kwargs
) -> typing.Generator[Path, None, None]:
    """
    Render a template to a pdf file.

    Args:
        source: Name of the template or a DjangoTemplate object.

    Returns:
        A path to the rendered pdf temporary file.
        This file will be deleted after the exiting the context.
    """

    if isinstance(source, str):
        source = get_template(source)
    if isinstance(source, DjangoTemplate) is False:
        raise TypeError(f"Expected source to be a string or DjangoTemplate. Got {type(source)}.")

    html = source.render(context).strip()
    html_file_path = Path(tempfile.gettempdir()).joinpath(f"{uuid4()}.html")
    html_file_path.write_text(html)

    try:
        with render_to_pdf(source=html_file_path.as_posix()) as pdf_file_path:
            yield pdf_file_path
    except BaseException as e:
        raise e
    finally:
        html_file_path.unlink()
