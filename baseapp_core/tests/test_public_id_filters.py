import uuid

import django_filters
import pytest
from django.http import QueryDict
from django.test import override_settings

from baseapp_core.rest_framework.filters import PublicIdFilter, PublicIdMultipleFilter
from testproject.testapp.models import DummyPublicIdChildModel, DummyPublicIdModel
from testproject.testapp.tests.factories import (
    DummyLegacyModelFactory,
    DummyPublicIdChildModelFactory,
)

pytestmark = pytest.mark.django_db


class ChildFilterSet(django_filters.FilterSet):
    id = PublicIdFilter()
    parent = PublicIdFilter()
    parents = PublicIdMultipleFilter(field_name="parent")
    previous_parent = PublicIdFilter(field_name="previous__parent")
    tag = PublicIdFilter(field_name="tags", model=DummyPublicIdModel, distinct=True)
    legacy = PublicIdFilter()

    class Meta:
        model = DummyPublicIdChildModel
        fields = []


def filter_children(
    params: dict,
) -> tuple[ChildFilterSet, list[DummyPublicIdChildModel] | None]:
    filterset = ChildFilterSet(params, queryset=DummyPublicIdChildModel.objects.order_by("pk"))
    return filterset, (list(filterset.qs) if filterset.is_valid() else None)


class TestPublicIdFilters:
    def test_filters_by_public_id(self) -> None:
        child, other = DummyPublicIdChildModelFactory.create_batch(2)
        next_child = DummyPublicIdChildModelFactory(previous=child)
        child.tags.add(other.parent)

        assert filter_children({"parent": str(child.parent.public_id)})[1] == [child]
        assert filter_children({"id": str(other.public_id)})[1] == [other]
        assert filter_children({"previous_parent": str(child.parent.public_id)})[1] == [next_child]
        assert filter_children({"tag": str(other.parent.public_id)})[1] == [child]

    def test_multiple_filter(self) -> None:
        first, second, _third = DummyPublicIdChildModelFactory.create_batch(3)
        ids = [str(first.parent.public_id), str(second.parent.public_id)]

        repeated = QueryDict(f"parents={ids[0]}&parents={ids[1]}")
        csv = QueryDict(f"parents={ids[0]},{ids[1]}")
        assert filter_children(repeated)[1] == [first, second]
        assert filter_children(csv)[1] == [first, second]
        assert filter_children(QueryDict("parents="))[1] is not None

    def test_accepts_pks_by_default(self) -> None:
        child = DummyPublicIdChildModelFactory()
        legacy = DummyLegacyModelFactory()
        child.legacy = legacy
        child.save()
        assert filter_children({"parent": str(child.parent.pk)})[1] == [child]
        assert filter_children({"legacy": str(legacy.pk)})[1] == [child]

    @override_settings(BASEAPP_PUBLIC_ID_ALLOW_PK_LOOKUP=False)
    def test_rejects_pks_when_disabled(self) -> None:
        child = DummyPublicIdChildModelFactory()
        filterset, rows = filter_children({"parent": str(child.parent.pk)})
        assert rows is None
        assert "parent" in filterset.errors

    def test_rejects_another_models_public_id(self) -> None:
        child = DummyPublicIdChildModelFactory()
        for params in (
            {"parent": str(child.public_id)},
            {"parents": str(child.public_id)},
            {"id": str(child.parent.public_id)},
        ):
            filterset, rows = filter_children(params)
            assert rows is None, params
            assert set(filterset.errors) == set(params)

    @pytest.mark.parametrize("value", ["abc", str(uuid.uuid4())])
    def test_rejects_invalid_values(self, value: str) -> None:
        filterset, rows = filter_children({"parent": value})
        assert rows is None

    def test_empty_value_does_not_filter(self) -> None:
        DummyPublicIdChildModelFactory.create_batch(2)
        assert len(filter_children({"parent": ""})[1]) == 2
