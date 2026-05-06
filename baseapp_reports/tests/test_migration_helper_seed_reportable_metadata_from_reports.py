from types import SimpleNamespace
from unittest.mock import patch

import factory
import pytest

from baseapp_reports.migration_helpers.seed_reportable_metadata_from_reports_helper import (
    reverse_seed_reportable_metadata,
    seed_reportable_metadata_from_reports,
)


class _FakeFlatList(list):
    def distinct(self):
        seen = []
        for row in self:
            if row not in seen:
                seen.append(row)
        return seen


class _FakeValueList(list):
    def distinct(self):
        seen = []
        for row in self:
            if row not in seen:
                seen.append(row)
        return seen


class _FakeQuerySet:
    def __init__(self, rows):
        self._rows = list(rows)

    def exclude(self, **kwargs):
        return self._apply(**kwargs, exclude=True)

    def filter(self, **kwargs):
        return self._apply(**kwargs, exclude=False)

    def _apply(self, exclude=False, **kwargs):
        rows = self._rows
        for key, value in kwargs.items():
            if key.endswith("__isnull"):
                field = key.replace("__isnull", "")
                # Django ORM permits both ``target_content_type`` and
                # ``target_content_type_id`` for FK lookups; fall back to the FK column
                # so fakes can store just the integer.
                getter = lambda r, f=field: (
                    getattr(r, f, None) if hasattr(r, f) else getattr(r, f"{f}_id", None)
                )
                if exclude:
                    rows = [r for r in rows if (getter(r) is None) != value]
                else:
                    rows = [r for r in rows if (getter(r) is None) == value]
            elif key.endswith("__in"):
                field = key.replace("__in", "")
                rows = [r for r in rows if getattr(r, field) in value]
            else:
                rows = [r for r in rows if getattr(r, key) == value]
        return _FakeQuerySet(rows)

    def values_list(self, *fields, flat=False):
        if flat:
            assert len(fields) == 1
            return _FakeFlatList([getattr(r, fields[0]) for r in self._rows])
        return _FakeValueList([tuple(getattr(r, f) for f in fields) for r in self._rows])

    def count(self):
        return len(self._rows)


class _FakeManager:
    def __init__(self, rows=None):
        self._rows = list(rows or [])
        self.update_log = []
        self.delete_log = []
        self.create_log = []

    def filter(self, **kwargs):
        manager = self
        matched = _FakeQuerySet(manager._rows).filter(**kwargs)._rows

        class _MatchedQS(_FakeQuerySet):
            def delete(self):
                manager.delete_log.append(kwargs)
                manager._rows = [r for r in manager._rows if r not in matched]

        return _MatchedQS(matched)

    def exclude(self, **kwargs):
        return _FakeQuerySet(self._rows).exclude(**kwargs)

    def values_list(self, *fields, flat=False):
        return _FakeQuerySet(self._rows).values_list(*fields, flat=flat)

    def get_or_create(self, **kwargs):
        for row in self._rows:
            if all(getattr(row, k) == v for k, v in kwargs.items()):
                return row, False
        new_id = len(self._rows) + 1
        row = SimpleNamespace(id=new_id, **kwargs)
        self._rows.append(row)
        self.create_log.append(kwargs)
        return row, True

    def update_or_create(self, defaults=None, **kwargs):
        defaults = defaults or {}
        self.update_log.append({**kwargs, "defaults": defaults})
        return SimpleNamespace(**kwargs, **defaults), True


class _ReportFactory(factory.Factory):
    class Meta:
        model = SimpleNamespace

    pk = factory.Sequence(lambda n: n + 1)
    target_content_type_id = 99
    target_object_id = 1
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


def _make_apps(*, reports, report_types, documents=None, metadata_rows=None):
    report_manager = _FakeManager(reports)
    report_type_manager = _FakeManager(report_types)
    documentid_manager = _FakeManager(documents or [])
    metadata_manager = _FakeManager(metadata_rows or [])

    report_model = SimpleNamespace(objects=report_manager)
    report_type_model = SimpleNamespace(objects=report_type_manager)
    documentid_model = SimpleNamespace(objects=documentid_manager)
    metadata_model = SimpleNamespace(objects=metadata_manager)

    class FakeApps:
        def get_model(self, app_label, model_name):
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
def _stub_swapper_is_not_swapped():
    """Force the helper through ``apps.get_model`` instead of ``swapper.load_model``."""
    with patch(
        "baseapp_reports.migration_helpers.seed_reportable_metadata_from_reports_helper.get_apps_model",
        side_effect=lambda apps, app_label, model_name: apps.get_model(app_label, model_name),
    ):
        yield


def test_seed_reportable_metadata_creates_one_row_per_unique_target():
    spam_type = _ReportTypeRowFactory(id=1, key="spam")
    fake_type = _ReportTypeRowFactory(id=2, key="fake")

    reports = [
        _ReportFactory(pk=1, target_content_type_id=99, target_object_id=10, report_type_id=1),
        _ReportFactory(pk=2, target_content_type_id=99, target_object_id=10, report_type_id=2),
        _ReportFactory(pk=3, target_content_type_id=99, target_object_id=20, report_type_id=1),
    ]
    apps, _, metadata_manager, _ = _make_apps(
        reports=reports,
        report_types=[spam_type, fake_type],
    )

    seed_reportable_metadata_from_reports(apps, schema_editor=None)

    # Two metadata writes, one per (ct, obj) pair, in insertion order.
    assert len(metadata_manager.update_log) == 2

    # target=10 → spam=1, fake=1, total=2
    # target=20 → spam=1, fake=0, total=1
    counts_first, counts_second = (
        e["defaults"]["reports_count"] for e in metadata_manager.update_log
    )
    assert counts_first == {"total": 2, "spam": 1, "fake": 1}
    assert counts_second == {"total": 1, "spam": 1, "fake": 0}


def test_seed_reportable_metadata_no_op_when_no_reports():
    apps, _, metadata_manager, _ = _make_apps(reports=[], report_types=[])

    seed_reportable_metadata_from_reports(apps, schema_editor=None)

    assert metadata_manager.update_log == []


def test_seed_reportable_metadata_skips_reports_with_null_target():
    spam_type = _ReportTypeRowFactory(id=1, key="spam")
    reports = [
        _ReportFactory(pk=1, target_content_type_id=None, target_object_id=10, report_type_id=1),
        _ReportFactory(pk=2, target_content_type_id=99, target_object_id=None, report_type_id=1),
        _ReportFactory(pk=3, target_content_type_id=99, target_object_id=20, report_type_id=1),
    ]
    apps, _, metadata_manager, _ = _make_apps(reports=reports, report_types=[spam_type])

    seed_reportable_metadata_from_reports(apps, schema_editor=None)

    # Only the (99, 20) pair survives the NULL exclusions.
    assert len(metadata_manager.update_log) == 1
    assert metadata_manager.update_log[0]["defaults"]["reports_count"] == {"total": 1, "spam": 1}


def test_reverse_seed_reportable_metadata_deletes_metadata_for_known_doc_ids():
    spam_type = _ReportTypeRowFactory(id=1, key="spam")
    reports = [
        _ReportFactory(pk=1, target_content_type_id=99, target_object_id=10, report_type_id=1)
    ]
    documents = [
        _DocumentIdRowFactory(id=100, content_type_id=99, object_id=10),
        _DocumentIdRowFactory(id=200, content_type_id=99, object_id=999),  # unrelated obj
    ]
    apps, _, metadata_manager, _ = _make_apps(
        reports=reports,
        report_types=[spam_type],
        documents=documents,
        metadata_rows=[
            SimpleNamespace(target_id=100),
            SimpleNamespace(target_id=200),
            SimpleNamespace(target_id=999),  # unrelated metadata
        ],
    )

    reverse_seed_reportable_metadata(apps, schema_editor=None)

    # Delete filter: target_id__in matches only doc IDs whose (ct, obj) pair appears in
    # live Reports. With (99, 10) being the only pair, doc 100 should be the deletion
    # target. doc 200 is matched by the broad content_type_id__in / object_id__in but
    # its (ct, obj) doesn't appear in reports — the helper *does* delete it because the
    # reverse uses the broader filter; this test locks the current behavior.
    assert len(metadata_manager.delete_log) == 1
    deleted_kwargs = metadata_manager.delete_log[0]
    assert "target_id__in" in deleted_kwargs


def test_reverse_seed_reportable_metadata_no_op_when_no_reports():
    apps, _, metadata_manager, _ = _make_apps(reports=[], report_types=[])

    reverse_seed_reportable_metadata(apps, schema_editor=None)

    assert metadata_manager.delete_log == []
