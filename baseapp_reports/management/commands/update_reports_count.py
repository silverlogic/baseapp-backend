import swapper
from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    """
    Recompute ``ReportableMetadata.reports_count`` for every target referenced by an
    existing Report. Useful after manual data edits or when seeding metadata for a
    project that is just opting into the plugin architecture.
    """

    help = "Recompute reports_count metadata for every reported target."

    def handle(self, *args, **options):
        Report = swapper.load_model("baseapp_reports", "Report")

        target_pairs = (
            Report.objects.exclude(target_content_type__isnull=True)
            .exclude(target_object_id__isnull=True)
            .values_list("target_content_type_id", "target_object_id")
            .distinct()
        )

        seen = 0
        for ct_id, obj_id in target_pairs:
            try:
                ct = ContentType.objects.get_for_id(ct_id)
            except ContentType.DoesNotExist:
                continue
            target = ct.get_object_for_this_type(pk=obj_id)
            Report.update_reports_count(target)
            seen += 1

        self.stdout.write(self.style.SUCCESS(f"Refreshed {seen} reportable target(s)."))
