import swapper
from django.core.management.base import BaseCommand

from baseapp_core.models import DocumentId


class Command(BaseCommand):
    """
    Recompute `ReportableMetadata.reports_count` for every target referenced by an
    existing Report. Useful after manual data edits or when seeding metadata for a
    project that is just opting into the plugin architecture.
    """

    help = "Recompute reports_count metadata for every reported target."

    def handle(self, *args, **options) -> None:
        Report = swapper.load_model("baseapp_reports", "Report")

        target_doc_ids = list(
            Report.objects.exclude(target_document__isnull=True)
            .values_list("target_document_id", flat=True)
            .distinct()
        )

        seen = 0
        for doc in DocumentId.objects.filter(pk__in=target_doc_ids).select_related("content_type"):
            target = doc.content_object
            if target is None:
                # Document points at a content_type/object_id that no longer exists in DB
                # (e.g. the underlying app was uninstalled). Skip rather than crash.
                continue
            Report.update_reports_count(target)
            seen += 1

        self.stdout.write(self.style.SUCCESS(f"Refreshed {seen} reportable target(s)."))
