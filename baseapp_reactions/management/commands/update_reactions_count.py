"""
Recompute `ReactableMetadata.reactions_count` for every distinct target referenced
by a `Reaction.target_document`.

Useful right after a backfill migration, or as a periodic sanity-recompute job
when reaction counters drift (e.g. due to direct SQL inserts that bypass the
`Reaction.save` write-through).
"""

import swapper
from django.core.management.base import BaseCommand

from baseapp_core.models import DocumentId

Reaction = swapper.load_model("baseapp_reactions", "Reaction")


class Command(BaseCommand):
    help = "Recompute ReactableMetadata.reactions_count for every distinct reaction target."

    def handle(self, *args, **options):
        target_doc_ids = (
            Reaction.objects.exclude(target_document__isnull=True)
            .values_list("target_document_id", flat=True)
            .distinct()
        )
        recomputed = 0
        skipped = 0
        for doc_id in target_doc_ids:
            try:
                doc = DocumentId.objects.get(pk=doc_id)
            except DocumentId.DoesNotExist:
                skipped += 1
                continue
            target = doc.content_object
            if target is None:
                skipped += 1
                continue
            Reaction.update_reactions_count(target)
            recomputed += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Recomputed reactions_count for {recomputed} target(s); skipped {skipped}."
            )
        )
