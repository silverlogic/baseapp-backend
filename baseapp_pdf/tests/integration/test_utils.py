from random import randint

import pytest
from django.utils import timezone

from baseapp_core.tests.fixtures import *  # noqa
from baseapp_pdf.exceptions import BaseAppBackendPDFRenderToPDFException
from baseapp_pdf.utils import (
    ensure_google_chrome_installed,
    render_template_to_pdf,
    render_to_pdf,
)

pytestmark = pytest.mark.django_db


@pytest.mark.usefixtures("responses_mock")
class TestUtils:
    def test_utils_ensure_google_chrome_installed(self):
        ensure_google_chrome_installed()

    def test_utils_render_to_pdf_succeeds_with_valid_url(self):
        with render_to_pdf(source="https://google.ca") as _:
            pass

    def test_utils_render_to_pdf_fails_with_invalid_url(self):
        try:
            with render_to_pdf(source="https://not.a.url") as _:
                pass
        except BaseAppBackendPDFRenderToPDFException:
            pass

    def test_utils_render_template_to_pdf(self):
        context = dict(
            pdf_title="Example PDF",
            pdf_margins="1cm 1cm",
            pdf_datetime=timezone.now(),
            pdf_header_data=dict(
                left=dict(
                    table_data=[
                        "Please Remit Payment To:",
                        "The SilverLogic",
                        "751 Park of Commerce Dr #126, Boca Raton, FL 33487, United States",
                        "+1 561-569-2366",
                    ]
                ),
                right=dict(
                    table_data=[
                        ("Invoice #", "BA-0000000001"),
                        ("Client Account Number:", "0000000001"),
                        ("Client Account Name:", "Awesome Client"),
                        ("Invoice Date", timezone.now() - timezone.timedelta(weeks=2)),
                    ]
                ),
            ),
            pdf_content=dict(
                title="Summary",
                table_data=[
                    dict(
                        title="Backend Charges",
                        items=[
                            (
                                f"Story {i + 1}",
                                float(randint(100, 1000)) + float(1 / randint(1, 10)),
                            )
                            for i in range(0, 24)
                        ],
                    ),
                    dict(
                        title="Web App(React) Charges",
                        items=[
                            (
                                f"Story {i + 1}",
                                float(randint(100, 1000)) + float(1 / randint(1, 10)),
                            )
                            for i in range(0, 24)
                        ],
                    ),
                    dict(
                        title="Android App Charges",
                        items=[
                            (
                                f"Story {i + 1}",
                                float(randint(100, 1000)) + float(1 / randint(1, 10)),
                            )
                            for i in range(0, 24)
                        ],
                    ),
                    dict(
                        title="iOS App Charges",
                        items=[
                            (
                                f"Story {i + 1}",
                                float(randint(100, 1000)) + float(1 / randint(1, 10)),
                            )
                            for i in range(0, 24)
                        ],
                    ),
                ],
            ),
        )
        with render_template_to_pdf(
            source="pdfs/render-template-to-pdf-example.html", context=context
        ) as _:
            pass
