import subprocess
from random import randint
from unittest import mock

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
    def test_utils_ensure_google_chrome_installed(self) -> None:
        ensure_google_chrome_installed()

    def test_utils_render_to_pdf_succeeds_with_valid_url(self) -> None:
        with render_to_pdf(source="https://google.ca") as _:
            pass

    def test_utils_render_to_pdf_fails_with_invalid_url(self) -> None:
        try:
            with render_to_pdf(source="https://not.a.url") as _:
                pass
        except BaseAppBackendPDFRenderToPDFException:
            pass

    def test_utils_render_to_pdf_wraps_a_chrome_failure(self) -> None:
        # Whether an unreachable URL makes Chrome exit non-zero or render an error page
        # depends on the network the suite runs on, so the failing branch is driven
        # directly rather than through DNS.
        error = subprocess.CalledProcessError(
            returncode=1, cmd=["google-chrome"], stderr=b"net::ERR_NAME_NOT_RESOLVED"
        )
        real_run = subprocess.run

        def fail_only_the_render(command, *args, **kwargs) -> subprocess.CompletedProcess:
            # `render_to_pdf` checks that Chrome is installed before rendering; that call
            # has to go through for the test to reach the branch under test.
            if "--version" in command:
                return real_run(command, *args, **kwargs)
            raise error

        with mock.patch("baseapp_pdf.utils.subprocess.run", side_effect=fail_only_the_render):
            with pytest.raises(BaseAppBackendPDFRenderToPDFException) as excinfo:
                with render_to_pdf(source="https://not.a.url") as _:
                    pass

        assert "ERR_NAME_NOT_RESOLVED" in str(excinfo.value)
        assert isinstance(excinfo.value.__cause__, subprocess.CalledProcessError)

    def test_utils_render_to_pdf_wraps_chrome_producing_no_file(self) -> None:
        # The other way Chrome fails: it exits zero and writes nothing. The cleanup in
        # `finally` must not turn that into a missing-file error of its own, which would
        # replace the exception that explains what went wrong.
        real_run = subprocess.run

        def succeed_without_writing_a_pdf(command, *args, **kwargs) -> subprocess.CompletedProcess:
            if "--version" in command:
                return real_run(command, *args, **kwargs)
            return subprocess.CompletedProcess(args=command, returncode=0, stdout=b"", stderr=b"")

        with mock.patch(
            "baseapp_pdf.utils.subprocess.run", side_effect=succeed_without_writing_a_pdf
        ):
            with pytest.raises(BaseAppBackendPDFRenderToPDFException) as excinfo:
                with render_to_pdf(source="https://not.a.url") as _:
                    pass

        assert "produced no PDF" in str(excinfo.value)
        assert isinstance(excinfo.value.__cause__, FileNotFoundError)

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
                        "title": "Backend Charges",
                        "items": [
                            (
                                f"Story {i + 1}",
                                float(randint(100, 1000)) + float(1 / randint(1, 10)),  # NOSONAR
                            )
                            for i in range(0, 24)
                        ],
                    },
                    {
                        "title": "Web App(React) Charges",
                        "items": [
                            (
                                f"Story {i + 1}",
                                float(randint(100, 1000)) + float(1 / randint(1, 10)),  # NOSONAR
                            )
                            for i in range(0, 24)
                        ],
                    },
                    {
                        "title": "Android App Charges",
                        "items": [
                            (
                                f"Story {i + 1}",
                                float(randint(100, 1000)) + float(1 / randint(1, 10)),  # NOSONAR
                            )
                            for i in range(0, 24)
                        ],
                    },
                    {
                        "title": "iOS App Charges",
                        "items": [
                            (
                                f"Story {i + 1}",
                                float(randint(100, 1000)) + float(1 / randint(1, 10)),  # NOSONAR
                            )
                            for i in range(0, 24)
                        ],
                    },
                ],
            },
        }
        with render_template_to_pdf(
            source="pdfs/render-template-to-pdf-example.html", context=context
        ) as _:
            pass
