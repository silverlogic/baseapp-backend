import tempfile
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path
from random import randint

import pytest
from django.template import engines
from django.test import override_settings
from django.utils import timezone
from pypdf import PdfReader

from baseapp_pdf.exceptions import BaseAppBackendPDFRenderToPDFException
from baseapp_pdf.utils import (
    chrome_available,
    ensure_google_chrome_installed,
    render_html_to_pdf,
    render_template_to_pdf,
    render_template_to_pdf_bytes,
    render_to_pdf,
)

# These drive a real Chrome (`BASEAPP_PDF_CHROME_BINARY`, `google-chrome` by default). Where
# none is installed they are skipped; the mocked tests in `tests/unit` cover the logic.
pytestmark = pytest.mark.skipif(not chrome_available(), reason="Chrome is not installed")


def pdf_text(pdf: bytes) -> str:
    return "\n".join(page.extract_text() for page in PdfReader(BytesIO(pdf)).pages)


def leftover_work_dirs() -> set[Path]:
    return set(Path(tempfile.gettempdir()).glob("baseapp_pdf_*"))


class TestUtils:
    def test_utils_ensure_google_chrome_installed(self) -> None:
        ensure_google_chrome_installed()

    def test_render_html_to_pdf(self) -> None:
        before = leftover_work_dirs()

        pdf = render_html_to_pdf("<h1>Invoice 42</h1><p>Café, déjà vu — naïve</p>")

        assert pdf.startswith(b"%PDF")
        text = pdf_text(pdf)
        assert "Invoice 42" in text
        assert "Café, déjà vu — naïve" in text
        assert leftover_work_dirs() == before

    def test_render_html_to_pdf_base_url(self, tmp_path: Path) -> None:
        (tmp_path / "style.css").write_text("p::after { content: ' from the stylesheet'; }")

        pdf = render_html_to_pdf(
            '<head><link rel="stylesheet" href="style.css"></head><p>Styled</p>',
            base_url=tmp_path.as_uri() + "/",
        )

        assert "Styled from the stylesheet" in pdf_text(pdf)

    @pytest.mark.parametrize("base_url", [None, "https://example.com/"])
    def test_base_url_keeps_standards_mode(self, base_url: str | None) -> None:
        # A `<base>` before the doctype used to drop the page into quirks mode, which
        # changes the box model and table layout.
        pdf = render_html_to_pdf(
            '<!DOCTYPE html><html lang="fr"><body><script>'
            "document.write('MODE ' + document.compatMode + ' LANG '"
            " + document.documentElement.lang + ' BASE ' + document.baseURI);"
            "</script></body></html>",
            base_url=base_url,
        )

        text = pdf_text(pdf)
        assert "MODE CSS1Compat" in text
        assert "LANG fr" in text
        if base_url:
            assert f"BASE {base_url}" in text

    @override_settings(BASEAPP_PDF_TIMEOUT=2)
    def test_timed_out_renders_leave_nothing_behind(self) -> None:
        # On a timeout only Chrome's main process used to be killed; its helpers kept
        # writing to the profile while it was removed, and the directory stayed.
        before = leftover_work_dirs()

        for _ in range(4):
            with pytest.raises(BaseAppBackendPDFRenderToPDFException, match="within 2 seconds"):
                render_html_to_pdf("<script>while (true) {}</script>")

        assert leftover_work_dirs() == before

    def test_concurrent_renders(self) -> None:
        documents = [f"Document number {i}" for i in range(4)]

        with ThreadPoolExecutor(max_workers=len(documents)) as executor:
            pdfs = list(executor.map(lambda text: render_html_to_pdf(f"<p>{text}</p>"), documents))

        for text, pdf in zip(documents, pdfs):
            assert text in pdf_text(pdf)

    def test_render_to_pdf_local_file(self, tmp_path: Path) -> None:
        html_file = tmp_path / "page.html"
        html_file.write_text("<p>From a file</p>")

        with render_to_pdf(source=html_file) as pdf_file_path:
            assert "From a file" in pdf_text(pdf_file_path.read_bytes())

        assert not pdf_file_path.exists()

    def test_render_to_pdf_missing_local_file(self, tmp_path: Path) -> None:
        with pytest.raises(BaseAppBackendPDFRenderToPDFException):
            with render_to_pdf(source=tmp_path / "missing.html"):
                pass

    def test_render_jinja2_template(self) -> None:
        template = engines["jinja2"].from_string("<p>{{ greeting }}, {{ name }}</p>")

        pdf = render_template_to_pdf_bytes(template, {"greeting": "Hello", "name": "Ada"})

        assert "Hello, Ada" in pdf_text(pdf)

    def test_utils_render_template_to_pdf(self) -> None:
        context = {
            "pdf_title": "Example PDF",
            "pdf_margins": "1cm 1cm",
            "pdf_datetime": timezone.now(),
            "pdf_header_data": {
                "left": {
                    "table_data": [
                        "Please Remit Payment To:",
                        "The SilverLogic",
                        "751 Park of Commerce Dr #126, Boca Raton, FL 33487, United States",
                        "+1 561-569-2366",
                    ]
                },
                "right": {
                    "table_data": [
                        ("Invoice #", "BA-0000000001"),
                        ("Client Account Number:", "0000000001"),
                        ("Client Account Name:", "Awesome Client"),
                        ("Invoice Date", timezone.now() - timezone.timedelta(weeks=2)),
                    ]
                },
            },
            "pdf_content": {
                "title": "Summary",
                "table_data": [
                    {
                        "title": title,
                        "items": [
                            (
                                f"Story {i + 1}",
                                float(randint(100, 1000)) + float(1 / randint(1, 10)),  # NOSONAR
                            )
                            for i in range(0, 24)
                        ],
                    }
                    for title in (
                        "Backend Charges",
                        "Web App(React) Charges",
                        "Android App Charges",
                        "iOS App Charges",
                    )
                ],
            },
        }
        with render_template_to_pdf(
            source="pdfs/render-template-to-pdf-example.html", context=context
        ) as pdf_file_path:
            assert "BA-0000000001" in pdf_text(pdf_file_path.read_bytes())
