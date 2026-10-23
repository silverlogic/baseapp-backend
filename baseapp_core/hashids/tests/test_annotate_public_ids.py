import pytest
from django.test import override_settings

from baseapp_core.hashids.strategies import annotate_public_ids
from testproject.testapp.models import DummyLegacyModel, DummyPublicIdChildModel
from testproject.testapp.tests.factories import (
    DummyLegacyModelFactory,
    DummyPublicIdChildModelFactory,
)

pytestmark = pytest.mark.django_db


def test_annotates_own_and_foreign_key_public_ids() -> None:
    previous = DummyPublicIdChildModelFactory()
    child = DummyPublicIdChildModelFactory(previous=previous)

    row = annotate_public_ids(
        DummyPublicIdChildModel.objects.all(), "parent", "previous__parent"
    ).get(pk=child.pk)

    assert row.mapped_public_id == child.public_id
    assert row.parent_public_id == child.parent.public_id
    assert row.previous__parent_public_id == previous.parent.public_id


def test_nullable_paths_keep_rows_and_annotate_none() -> None:
    child = DummyPublicIdChildModelFactory(previous=None)

    rows = list(annotate_public_ids(DummyPublicIdChildModel.objects.all(), "previous__parent"))

    assert [row.pk for row in rows] == [child.pk]
    assert rows[0].previous__parent_public_id is None


def test_public_id_reads_the_annotation(django_assert_num_queries) -> None:
    DummyPublicIdChildModelFactory.create_batch(3)

    with django_assert_num_queries(1):
        rows = list(annotate_public_ids(DummyPublicIdChildModel.objects.all()))
        assert all(row.public_id is not None for row in rows)


def test_include_self_false_skips_mapped_public_id() -> None:
    DummyPublicIdChildModelFactory()

    queryset = annotate_public_ids(
        DummyPublicIdChildModel.objects.all(), "parent", include_self=False
    )

    assert set(queryset.query.annotations) == {"parent_public_id"}


def test_is_idempotent() -> None:
    queryset = annotate_public_ids(DummyPublicIdChildModel.objects.all(), "parent")

    assert annotate_public_ids(queryset, "parent") is queryset


def test_skips_models_without_public_ids() -> None:
    DummyLegacyModelFactory()

    queryset = DummyLegacyModel.objects.all()
    assert annotate_public_ids(queryset) is queryset
    child_queryset = annotate_public_ids(DummyPublicIdChildModel.objects.all(), "legacy")
    assert "legacy_public_id" not in child_queryset.query.annotations


@override_settings(ENABLE_PUBLIC_ID_LOGIC=False)
def test_adds_nothing_when_public_id_logic_is_disabled() -> None:
    queryset = DummyPublicIdChildModel.objects.all()

    assert annotate_public_ids(queryset, "parent") is queryset


@pytest.mark.parametrize("path", ["tags", "next_children", "name", "parent__name"])
def test_rejects_paths_that_are_not_to_one_relations(path: str) -> None:
    with pytest.raises(ValueError):
        annotate_public_ids(DummyPublicIdChildModel.objects.all(), path)
