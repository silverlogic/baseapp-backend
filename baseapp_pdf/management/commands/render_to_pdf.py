import traceback
from pathlib import Path

from django.core.management.base import BaseCommand

from baseapp_pdf.utils import render_to_pdf


class Command(BaseCommand):
    help = "Render to PDF"

    def __init__(self, *args, **kwargs):
        super(Command, self).__init__(*args, **kwargs)

    def add_arguments(self, parser):
        parser.add_argument(
            "--source", type=str, required=True, help="Local html file path or a url string"
        )
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
        source = Path(options.get("source"))
        destination = Path(options.get("destination") or Path.cwd())
        if destination.is_dir() is False:
            raise ValueError(f"Destination must be a directory! {destination}")
        self.render_to_pdf(source=source, destination=destination)

    def render_to_pdf(self, source: str | Path, destination: Path):
        with render_to_pdf(source=source) as pdf_file_path:
            output_file_path = destination.joinpath(pdf_file_path.name)
            if output_file_path.exists():
                output_file_path.unlink()
            output_file_path.write_bytes(pdf_file_path.read_bytes())
            size_mb = output_file_path.stat().st_size / (1024 * 1024)
            self.stdout.write(
                self.style.SUCCESS(f"PDF generated at {output_file_path} size:{size_mb:.2f} MB")
            )
