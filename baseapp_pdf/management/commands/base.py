import traceback
from pathlib import Path

from django.core.management.base import BaseCommand


class BasePDFCommand(BaseCommand):  # pragma: no cover
    def handle(self, *args, **options):
        try:
            self._handle(*args, **options)
        except KeyboardInterrupt:
            self.stdout.write("\r\n")
        except (
            Exception
        ):  # NOSONAR - S5754: management command handler intentionally catches all exceptions to print stacktrace
            self.stdout.write("\r\n")
            self.stdout.write(self.style.ERROR(traceback.format_exc()))

    def _write_pdf_output(self, pdf_file_path: Path, destination: Path) -> None:
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
