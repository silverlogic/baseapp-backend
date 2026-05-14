from pathlib import Path
from random import randint

from django.utils import timezone

from baseapp_pdf.management.commands.base import BasePDFCommand
from baseapp_pdf.utils import render_template_to_pdf


class Command(BasePDFCommand):  # pragma: no cover
    help = "Render Example Templateto PDF"

    def __init__(self, *args, **kwargs):
        super(Command, self).__init__(*args, **kwargs)

    def add_arguments(self, parser):
        parser.add_argument(
            "--destination", type=str, help="The destination directory_path. Defaults to cwd."
        )

    def _handle(self, *args, **options):
        destination = Path(options.get("destination") or Path.cwd())
        if destination.is_dir() is False:
            raise ValueError(f"Destination must be a directory! {destination}")
        self.render_example_template_to_pdf(destination=destination)

    def render_example_template_to_pdf(self, destination: Path):
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
        ) as pdf_file_path:
            resolved_destination = destination.resolve()
            output_file_path = (
                resolved_destination / pdf_file_path.name
            ).resolve()  # NOSONAR - S2083: path validated by is_relative_to below; admin-only management command
            if not output_file_path.is_relative_to(resolved_destination):
                raise ValueError(f"Output path escapes destination directory: {output_file_path}")
            if output_file_path.exists():
                output_file_path.unlink()  # NOSONAR - S2083
            output_file_path.write_bytes(pdf_file_path.read_bytes())  # NOSONAR - S2083
            size_mb = output_file_path.stat().st_size / (1024 * 1024)
            self.stdout.write(
                self.style.SUCCESS(f"PDF generated at {output_file_path} size:{size_mb:.2f} MB")
            )
