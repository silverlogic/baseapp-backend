"""The Mention through-table is itself a `DocumentIdMixin` model, so every row
must be registered in the central `DocumentId` registry by the insert/delete
pgtriggers added alongside the `target_document` refactor.
"""

import pytest
import swapper
from django.contrib.contenttypes.models import ContentType

from baseapp_comments.tests.factories import CommentFactory
from baseapp_core.backfill import backfill_model_document_ids
from baseapp_core.models import DocumentId
from baseapp_profiles.tests.factories import ProfileFactory

pytestmark = pytest.mark.django_db

Mention = swapper.load_model("baseapp_mentions", "Mention")


def test_creating_mention_registers_it_in_document_id_registry() -> None:
    target_doc = DocumentId.get_or_create_for_object(CommentFactory())
    mention = Mention.objects.create(profile=ProfileFactory(), target_document=target_doc)

    ct = ContentType.objects.get_for_model(Mention)
    assert DocumentId.objects.filter(content_type=ct, object_id=mention.pk).exists()


def test_deleting_mention_removes_its_document_id() -> None:
    target_doc = DocumentId.get_or_create_for_object(CommentFactory())
    mention = Mention.objects.create(profile=ProfileFactory(), target_document=target_doc)
    ct = ContentType.objects.get_for_model(Mention)
    pk = mention.pk

    mention.delete()

    assert not DocumentId.objects.filter(content_type=ct, object_id=pk).exists()


def test_backfill_registers_rows_that_predate_the_trigger() -> None:
    """The migration's `backfill_model_document_ids` call must register Mention
    rows that existed before the insert trigger was added. Simulate that legacy
    state by deleting the auto-created DocumentId rows, then backfill.
    """
    target_doc = DocumentId.get_or_create_for_object(CommentFactory())
    mentions = [
        Mention.objects.create(profile=ProfileFactory(), target_document=target_doc)
        for _ in range(3)
    ]
    ct = ContentType.objects.get_for_model(Mention)
    object_ids = [m.pk for m in mentions]

    # Drop the trigger-created registry rows to mimic pre-trigger data.
    DocumentId.objects.filter(content_type=ct, object_id__in=object_ids).delete()
    assert not DocumentId.objects.filter(content_type=ct, object_id__in=object_ids).exists()

    created = backfill_model_document_ids(model=Mention, DocumentId=DocumentId)

    assert created == 3
    for pk in object_ids:
        assert DocumentId.objects.filter(content_type=ct, object_id=pk).exists()
