import traceback
from pathlib import Path
from random import randint

from django.core.management.base import BaseCommand
from django.utils import timezone

from baseapp_pdf.utils import render_template_to_pdf


class Command(BaseCommand):
    help = "Render Example Templateto PDF"

    def __init__(self, *args, **kwargs):
        super(Command, self).__init__(*args, **kwargs)

    def add_arguments(self, parser):
        parser.add_argument(
            "--destination", type=str, help="The destination directory_path. Defaults to cwd."
        )

    def handle(self, *args, **options):
        try:
            self._handle(*args, **options)
        except BaseException as e:
            self.stdout.write("\r\n")
            if isinstance(e, KeyboardInterrupt):
                return
            self.stdout.write(self.style.ERROR(traceback.format_exc()))

    def _handle(self, *args, **options):
        destination = Path(options.get("destination") or Path.cwd())
        if destination.is_dir() is False:
            raise ValueError(f"Destination must be a directory! {destination}")
        self.render_example_template_to_pdf(destination=destination)

    def render_example_template_to_pdf(self, destination: Path):
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
        ) as pdf_file_path:
            output_file_path = destination.joinpath(pdf_file_path.name)
            if output_file_path.exists():
                output_file_path.unlink()
            output_file_path.write_bytes(pdf_file_path.read_bytes())
            size_mb = output_file_path.stat().st_size / (1024 * 1024)
            self.stdout.write(
                self.style.SUCCESS(f"PDF generated at {output_file_path} size:{size_mb:.2f} MB")
            )
