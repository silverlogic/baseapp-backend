from collections.abc import Generator
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import factory
import pytest

from baseapp_reports.migration_helpers.seed_reportable_metadata_from_reports_helper import (
    reverse_seed_reportable_metadata,
    seed_reportable_metadata_from_reports,
)


class _FakeFlatList(list):
    def distinct(self) -> list[Any]:
        seen = []
        for row in self:
            if row not in seen:
                seen.append(row)
        return seen


class _FakeValueList(list):
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
                    # Django ORM permits both `target_content_type` and
                    # `target_content_type_id` for FK lookups; fall back to the FK
                    # column so fakes can store just the integer.
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

    def values_list(self, *fields, flat=False) -> _FakeFlatList | _FakeValueList:
        if flat:
            assert len(fields) == 1
            return _FakeFlatList([getattr(r, fields[0]) for r in self._rows])
        return _FakeValueList([tuple(getattr(r, f) for f in fields) for r in self._rows])

    def count(self) -> int:
        return len(self._rows)


class _FakeManager:
    def __init__(self, rows=None) -> None:
        self._rows = list(rows or [])
        self.update_log = []
        self.delete_log = []
        self.create_log = []

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

    def values_list(self, *fields, flat=False) -> _FakeFlatList | _FakeValueList:
        return _FakeQuerySet(self._rows).values_list(*fields, flat=flat)

    def get_or_create(self, **kwargs) -> tuple[SimpleNamespace, bool]:
        for row in self._rows:
            if all(getattr(row, k) == v for k, v in kwargs.items()):
                return row, False
        new_id = len(self._rows) + 1
        row = SimpleNamespace(id=new_id, **kwargs)
        self._rows.append(row)
        self.create_log.append(kwargs)
        return row, True

    def update_or_create(self, defaults=None, **kwargs) -> tuple[SimpleNamespace, bool]:
        defaults = defaults or {}
        self.update_log.append({**kwargs, "defaults": defaults})
        return SimpleNamespace(**kwargs, **defaults), True


class _ReportFactory(factory.Factory):
    class Meta:
        model = SimpleNamespace

    pk = factory.Sequence(lambda n: n + 1)
    target_document_id = 1000
    report_type_id = None


class _ReportTypeRowFactory(factory.Factory):
    class Meta:
        model = SimpleNamespace

    id = factory.Sequence(lambda n: n + 1)
    key = "spam"


class _DocumentIdRowFactory(factory.Factory):
    class Meta:
        model = SimpleNamespace

    id = 1000
    content_type_id = 99
    object_id = 1


def _make_apps(
    *, reports, report_types, documents=None, metadata_rows=None
) -> tuple[Any, _FakeManager, _FakeManager, _FakeManager]:
    report_manager = _FakeManager(reports)
    report_type_manager = _FakeManager(report_types)
    documentid_manager = _FakeManager(documents or [])
    metadata_manager = _FakeManager(metadata_rows or [])

    report_model = SimpleNamespace(objects=report_manager)
    report_type_model = SimpleNamespace(objects=report_type_manager)
    documentid_model = SimpleNamespace(objects=documentid_manager)
    metadata_model = SimpleNamespace(objects=metadata_manager)

    class FakeApps:
        def get_model(self, app_label, model_name) -> SimpleNamespace:
            mapping = {
                ("baseapp_reports", "Report"): report_model,
                ("baseapp_reports", "ReportType"): report_type_model,
                ("baseapp_reports", "ReportableMetadata"): metadata_model,
                ("baseapp_core", "DocumentId"): documentid_model,
                # Swapped names (BASEAPP_REPORTS_*_MODEL points at "reports.*"):
                ("reports", "Report"): report_model,
                ("reports", "ReportType"): report_type_model,
                ("reports", "ReportableMetadata"): metadata_model,
            }
            return mapping[(app_label, model_name)]

    return FakeApps(), report_manager, metadata_manager, documentid_manager


@pytest.fixture(autouse=True)
def _stub_swapper_is_not_swapped() -> Generator[None, None, None]:
    """Force the helper through `apps.get_model` instead of `swapper.load_model`."""
    with patch(
        "baseapp_reports.migration_helpers.seed_reportable_metadata_from_reports_helper.get_apps_model",
        side_effect=lambda apps, app_label, model_name: apps.get_model(app_label, model_name),
    ):
        yield


def test_seed_reportable_metadata_creates_one_row_per_unique_target() -> None:
    spam_type = _ReportTypeRowFactory(id=1, key="spam")
    fake_type = _ReportTypeRowFactory(id=2, key="fake")

    reports = [
        _ReportFactory(pk=1, target_document_id=10, report_type_id=1),
        _ReportFactory(pk=2, target_document_id=10, report_type_id=2),
        _ReportFactory(pk=3, target_document_id=20, report_type_id=1),
    ]
    apps, _, metadata_manager, _ = _make_apps(
        reports=reports,
        report_types=[spam_type, fake_type],
    )

    seed_reportable_metadata_from_reports(apps, schema_editor=None)

    # Two metadata writes, one per `target_document` reference, in insertion order.
    assert len(metadata_manager.update_log) == 2

    # target_document=10 → spam=1, fake=1, total=2
    # target_document=20 → spam=1, fake=0, total=1
    counts_first, counts_second = (
        e["defaults"]["reports_count"] for e in metadata_manager.update_log
    )
    assert counts_first == {"total": 2, "spam": 1, "fake": 1}
    assert counts_second == {"total": 1, "spam": 1, "fake": 0}

    # And the metadata rows are keyed by `target_id`, which is the DocumentId pk.
    assert [e["target_id"] for e in metadata_manager.update_log] == [10, 20]


def test_seed_reportable_metadata_no_op_when_no_reports() -> None:
    apps, _, metadata_manager, _ = _make_apps(reports=[], report_types=[])

    seed_reportable_metadata_from_reports(apps, schema_editor=None)

    assert metadata_manager.update_log == []


def test_seed_reportable_metadata_skips_reports_with_null_target() -> None:
    spam_type = _ReportTypeRowFactory(id=1, key="spam")
    reports = [
        _ReportFactory(pk=1, target_document_id=None, report_type_id=1),
        _ReportFactory(pk=2, target_document_id=20, report_type_id=1),
    ]
    apps, _, metadata_manager, _ = _make_apps(reports=reports, report_types=[spam_type])

    seed_reportable_metadata_from_reports(apps, schema_editor=None)

    # Only the report with a non-null target_document survives the exclusion.
    assert len(metadata_manager.update_log) == 1
    assert metadata_manager.update_log[0]["target_id"] == 20
    assert metadata_manager.update_log[0]["defaults"]["reports_count"] == {"total": 1, "spam": 1}


def test_reverse_seed_reportable_metadata_deletes_metadata_for_known_doc_ids() -> None:
    spam_type = _ReportTypeRowFactory(id=1, key="spam")
    reports = [
        _ReportFactory(pk=1, target_document_id=100, report_type_id=1),
    ]
    apps, _, metadata_manager, _ = _make_apps(
        reports=reports,
        report_types=[spam_type],
        metadata_rows=[
            SimpleNamespace(target_id=100),
            SimpleNamespace(target_id=999),  # unrelated metadata
        ],
    )

    reverse_seed_reportable_metadata(apps, schema_editor=None)

    # Delete filter: `target_id__in` matches only doc IDs that appear as a Report's
    # `target_document`. With only doc 100 referenced, doc 999 is left untouched.
    assert len(metadata_manager.delete_log) == 1
    deleted_kwargs = metadata_manager.delete_log[0]
    assert deleted_kwargs == {"target_id__in": [100]}


def test_reverse_seed_reportable_metadata_no_op_when_no_reports() -> None:
    apps, _, metadata_manager, _ = _make_apps(reports=[], report_types=[])

    reverse_seed_reportable_metadata(apps, schema_editor=None)

    assert metadata_manager.delete_log == []
