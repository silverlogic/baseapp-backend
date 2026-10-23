import pytest
from django.contrib.contenttypes.models import ContentType
from django.test import override_settings

from baseapp_core.hashids.strategies import (
    annotate_public_ids,
    get_annotated_public_id,
)
from baseapp_core.hashids.strategies.public_id import PublicIdQuerysetAnnotatorStrategy
from testproject.testapp.models import (
    DummyLegacyModel,
    DummyPublicIdChildModel,
    DummyPublicIdModel,
)
from testproject.testapp.tests.factories import (
    DummyLegacyModelFactory,
    DummyPublicIdChildModelFactory,
    DummyPublicIdModelFactory,
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
    # The key of each relation on the paths, as loaded.
    assert row.parent_public_id_pk == child.parent_id
    assert row.previous_public_id_pk == previous.pk
    assert row.previous__parent_public_id_pk == previous.parent_id


def test_nullable_paths_keep_rows_and_annotate_none() -> None:
    child = DummyPublicIdChildModelFactory(previous=None)

    rows = list(annotate_public_ids(DummyPublicIdChildModel.objects.all(), "previous__parent"))

    assert [row.pk for row in rows] == [child.pk]
    assert rows[0].previous__parent_public_id is None


def test_public_id_reads_the_annotation(django_assert_num_queries) -> None:
    DummyPublicIdChildModelFactory.create_batch(3)
    # Warm the content type cache, so the count does not depend on test order.
    ContentType.objects.get_for_model(DummyPublicIdChildModel)

    with django_assert_num_queries(1):
        rows = list(annotate_public_ids(DummyPublicIdChildModel.objects.all()))
        assert all(row.public_id is not None for row in rows)


def test_include_self_false_skips_mapped_public_id() -> None:
    DummyPublicIdChildModelFactory()

    queryset = annotate_public_ids(
        DummyPublicIdChildModel.objects.all(), "parent", include_self=False
    )

    assert set(queryset.query.annotations) == {"parent_public_id", "parent_public_id_pk"}


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


class TestGetAnnotatedPublicId:
    def load(self, queryset, pk: int, *paths: str) -> DummyPublicIdChildModel:
        return annotate_public_ids(queryset, *paths).get(pk=pk)

    def test_reads_the_annotation(self, django_assert_num_queries) -> None:
        child = DummyPublicIdChildModelFactory(previous=DummyPublicIdChildModelFactory())
        expected = (child.parent.public_id, child.previous.parent.public_id)
        row = self.load(
            DummyPublicIdChildModel.objects.all(), child.pk, "parent", "previous__parent"
        )

        with django_assert_num_queries(0):
            assert get_annotated_public_id(row, "parent") == expected[0]
            assert get_annotated_public_id(row, "previous__parent") == expected[1]

    def test_ignores_a_reassigned_foreign_key(self) -> None:
        child = DummyPublicIdChildModelFactory()
        other = DummyPublicIdModelFactory()

        for queryset in (
            DummyPublicIdChildModel.objects.all(),
            DummyPublicIdChildModel.objects.select_related("parent"),
        ):
            row = self.load(queryset, child.pk, "parent")
            row.parent = other
            assert get_annotated_public_id(row, "parent") is None

            row = self.load(queryset, child.pk, "parent")
            row.parent_id = other.pk
            assert get_annotated_public_id(row, "parent") is None

            row = self.load(queryset, child.pk, "parent")
            row.parent = child.parent
            assert get_annotated_public_id(row, "parent") == child.parent.public_id

    def test_ignores_a_reassigned_relation_along_the_path(self) -> None:
        child = DummyPublicIdChildModelFactory(previous=DummyPublicIdChildModelFactory())
        other_previous = DummyPublicIdChildModelFactory()

        row = self.load(DummyPublicIdChildModel.objects.all(), child.pk, "previous__parent")
        row.previous = other_previous
        assert get_annotated_public_id(row, "previous__parent") is None

        row = self.load(DummyPublicIdChildModel.objects.all(), child.pk, "previous__parent")
        row.previous = None
        assert get_annotated_public_id(row, "previous__parent") is None

        row = self.load(
            DummyPublicIdChildModel.objects.select_related("previous"),
            child.pk,
            "previous__parent",
        )
        row.previous.parent = other_previous.parent
        assert get_annotated_public_id(row, "previous__parent") is None

    def test_needs_the_loaded_keys(self) -> None:
        child = DummyPublicIdChildModelFactory()
        annotations = PublicIdQuerysetAnnotatorStrategy().get_annotations(
            DummyPublicIdModel, field="parent", alias="parent_public_id"
        )
        row = DummyPublicIdChildModel.objects.annotate(**annotations).get(pk=child.pk)

        assert row.parent_public_id == child.parent.public_id
        assert get_annotated_public_id(row, "parent") is None

    def test_none_without_the_annotation(self) -> None:
        child = DummyPublicIdChildModelFactory()
        assert get_annotated_public_id(child, "parent") is None
