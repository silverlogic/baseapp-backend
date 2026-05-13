import traceback

from django.core.management.base import BaseCommand


class BasePDFCommand(BaseCommand):  # pragma: no cover
    def handle(self, *args, **options):
        try:
            self._handle(*args, **options)
        except KeyboardInterrupt:
            self.stdout.write("\r\n")
        except Exception:
            self.stdout.write("\r\n")
            self.stdout.write(self.style.ERROR(traceback.format_exc()))
