from pathlib import Path

from baseapp_pdf.management.commands.base import BasePDFCommand
from baseapp_pdf.utils import render_to_pdf


class Command(BasePDFCommand):  # pragma: no cover
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

    def _handle(self, *args, **options):
        source = Path(options.get("source"))
        destination = Path(options.get("destination") or Path.cwd())
        if destination.is_dir() is False:
            raise ValueError(f"Destination must be a directory! {destination}")
        self.render_to_pdf(source=source, destination=destination)

    def render_to_pdf(self, source: str | Path, destination: Path):
        with render_to_pdf(source=source) as pdf_file_path:
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
