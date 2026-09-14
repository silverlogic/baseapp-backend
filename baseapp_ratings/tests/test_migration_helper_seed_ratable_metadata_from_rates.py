from collections.abc import Generator
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import factory
import pytest

from baseapp_ratings.migration_helpers.seed_ratable_metadata_from_rates_helper import (
    reverse_seed_ratable_metadata,
    seed_ratable_metadata_from_rates,
)


class _FakeFlatList(list):
    def distinct(self) -> list[Any]:
        seen = []
        for row in self:
            if row not in seen:
                seen.append(row)
        return seen


class _FakeQuerySet:
    def __init__(self, rows) -> None:
        self._rows = list(rows)

    def exclude(self, **kwargs) -> "_FakeQuerySet":
        return self._apply(**kwargs, exclude=True)

    def filter(self, **kwargs) -> "_FakeQuerySet":
        return self._apply(**kwargs, exclude=False)

    def _apply(self, exclude=False, **kwargs) -> "_FakeQuerySet":
        rows = self._rows
        for key, value in kwargs.items():
            if key.endswith("__isnull"):
                field = key.replace("__isnull", "")

                def _is_null(row, _f=field) -> bool:
                    # Django ORM accepts both `<field>` and `<field>_id` for FK lookups;
                    # fall back to the FK column so fakes can store just the integer.
                    if hasattr(row, _f):
                        return getattr(row, _f) is None
                    return getattr(row, f"{_f}_id", None) is None

                if exclude:
                    rows = [r for r in rows if _is_null(r) != value]
                else:
                    rows = [r for r in rows if _is_null(r) == value]
            elif key.endswith("__in"):
                field = key.replace("__in", "")
                rows = [r for r in rows if getattr(r, field) in value]
            else:
                rows = [r for r in rows if getattr(r, key) == value]
        return _FakeQuerySet(rows)

    def values_list(self, *fields, flat=False) -> _FakeFlatList | list[tuple[Any, ...]]:
        if flat:
            assert len(fields) == 1
            return _FakeFlatList([getattr(r, fields[0]) for r in self._rows])
        return [tuple(getattr(r, f) for f in fields) for r in self._rows]

    def count(self) -> int:
        return len(self._rows)


class _FakeManager:
    def __init__(self, rows=None) -> None:
        self._rows = list(rows or [])
        self.update_log = []
        self.delete_log = []

    def filter(self, **kwargs) -> _FakeQuerySet:
        manager = self
        matched = _FakeQuerySet(manager._rows).filter(**kwargs)._rows

        class _MatchedQS(_FakeQuerySet):
            def delete(self) -> None:
                manager.delete_log.append(kwargs)
                manager._rows = [r for r in manager._rows if r not in matched]

        return _MatchedQS(matched)

    def exclude(self, **kwargs) -> _FakeQuerySet:
        return _FakeQuerySet(self._rows).exclude(**kwargs)

    def values_list(self, *fields, flat=False) -> _FakeFlatList | list[tuple[Any, ...]]:
        return _FakeQuerySet(self._rows).values_list(*fields, flat=flat)

    def update_or_create(self, defaults=None, **kwargs) -> tuple[SimpleNamespace, bool]:
        defaults = defaults or {}
        self.update_log.append({**kwargs, "defaults": defaults})
        return SimpleNamespace(**kwargs, **defaults), True


class _RateFactory(factory.Factory):
    class Meta:
        model = SimpleNamespace

    pk = factory.Sequence(lambda n: n + 1)
    target_document_id = 1000
    value = 0


def _make_apps(*, rates, metadata_rows=None) -> tuple[Any, _FakeManager, _FakeManager]:
    rate_manager = _FakeManager(rates)
    metadata_manager = _FakeManager(metadata_rows or [])

    rate_model = SimpleNamespace(objects=rate_manager)
    metadata_model = SimpleNamespace(objects=metadata_manager)

    class FakeApps:
        def get_model(self, app_label, model_name) -> SimpleNamespace:
            mapping = {
                ("baseapp_ratings", "Rate"): rate_model,
                ("baseapp_ratings", "RatableMetadata"): metadata_model,
                # Swapped names (BASEAPP_RATINGS_*_MODEL points at "ratings.*"):
                ("ratings", "Rate"): rate_model,
                ("ratings", "RatableMetadata"): metadata_model,
            }
            return mapping[(app_label, model_name)]

    return FakeApps(), rate_manager, metadata_manager


@pytest.fixture(autouse=True)
def _stub_swapper_is_not_swapped() -> Generator[None, None, None]:
    """Force the helper through `apps.get_model` instead of `swapper.load_model`."""
    with patch(
        "baseapp_ratings.migration_helpers.seed_ratable_metadata_from_rates_helper.get_apps_model",
        side_effect=lambda apps, app_label, model_name: apps.get_model(app_label, model_name),
    ):
        yield


def test_seed_ratable_metadata_creates_one_row_per_unique_target() -> None:
    rates = [
        _RateFactory(pk=1, target_document_id=10, value=4),
        _RateFactory(pk=2, target_document_id=10, value=2),
        _RateFactory(pk=3, target_document_id=20, value=5),
    ]
    apps, _, metadata_manager = _make_apps(rates=rates)

    seed_ratable_metadata_from_rates(apps, schema_editor=None)

    # Two metadata writes, one per `target_document` reference, in insertion order.
    assert len(metadata_manager.update_log) == 2

    first, second = metadata_manager.update_log
    # target_document=10 → count=2, sum=6, avg=3
    assert first["target_id"] == 10
    assert first["defaults"] == {"ratings_count": 2, "ratings_sum": 6, "ratings_average": 3.0}
    # target_document=20 → count=1, sum=5, avg=5
    assert second["target_id"] == 20
    assert second["defaults"] == {"ratings_count": 1, "ratings_sum": 5, "ratings_average": 5.0}


def test_seed_ratable_metadata_no_op_when_no_rates() -> None:
    apps, _, metadata_manager = _make_apps(rates=[])

    seed_ratable_metadata_from_rates(apps, schema_editor=None)

    assert metadata_manager.update_log == []


def test_seed_ratable_metadata_skips_rates_with_null_target() -> None:
    rates = [
        _RateFactory(pk=1, target_document_id=None, value=3),
        _RateFactory(pk=2, target_document_id=20, value=4),
    ]
    apps, _, metadata_manager = _make_apps(rates=rates)

    seed_ratable_metadata_from_rates(apps, schema_editor=None)

    # Only the rate with a non-null target_document survives the exclusion.
    assert len(metadata_manager.update_log) == 1
    assert metadata_manager.update_log[0]["target_id"] == 20
    assert metadata_manager.update_log[0]["defaults"] == {
        "ratings_count": 1,
        "ratings_sum": 4,
        "ratings_average": 4.0,
    }


def test_reverse_seed_ratable_metadata_deletes_metadata_for_known_doc_ids() -> None:
    rates = [_RateFactory(pk=1, target_document_id=100, value=5)]
    apps, _, metadata_manager = _make_apps(
        rates=rates,
        metadata_rows=[
            SimpleNamespace(target_id=100),
            SimpleNamespace(target_id=999),  # unrelated metadata
        ],
    )

    reverse_seed_ratable_metadata(apps, schema_editor=None)

    assert len(metadata_manager.delete_log) == 1
    deleted_kwargs = metadata_manager.delete_log[0]
    assert deleted_kwargs == {"target_id__in": [100]}


def test_reverse_seed_ratable_metadata_no_op_when_no_rates() -> None:
    apps, _, metadata_manager = _make_apps(rates=[])

    reverse_seed_ratable_metadata(apps, schema_editor=None)

    assert metadata_manager.delete_log == []
