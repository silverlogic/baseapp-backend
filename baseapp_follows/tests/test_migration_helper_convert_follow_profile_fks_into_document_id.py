from types import SimpleNamespace
from unittest.mock import patch

import factory
import pytest

from baseapp_follows.migration_helpers.convert_follow_profile_fks_into_document_id_helper import (
    assert_all_follow_rows_reference_document_ids,
    migrate_follow_profile_fks_to_document_id,
    reverse_migrate_follow_document_id_fks_to_profile,
)


class _FakeQuerySet:
    def __init__(self, rows):
        self._rows = list(rows)

    def using(self, _alias):
        return self

    def all(self):
        return self

    def count(self):
        return len(self._rows)

    def exclude(self, **kwargs):
        return self._apply(**kwargs, exclude=True)

    def filter(self, **kwargs):
        return self._apply(**kwargs, exclude=False)

    def _apply(self, exclude=False, **kwargs):
        rows = self._rows
        for key, value in kwargs.items():
            if key.endswith("__isnull"):
                field = key.replace("__isnull", "")
                if exclude:
                    rows = [r for r in rows if (getattr(r, field, None) is None) != value]
                else:
                    rows = [r for r in rows if (getattr(r, field, None) is None) == value]
            else:
                rows = [r for r in rows if getattr(r, key) == value]
        return _FakeQuerySet(rows)

    def values(self, *fields):
        return [{f: getattr(r, f) for f in fields} for r in self._rows]

    def values_list(self, *fields, flat=False):
        if flat:
            assert len(fields) == 1
            return _FakeFlatList([getattr(r, fields[0]) for r in self._rows])
        return _FakeValueList([tuple(getattr(r, f) for f in fields) for r in self._rows])

    def __iter__(self):
        return iter(self._rows)

    def iterator(self, chunk_size=None):
        # Real Django `QuerySet.iterator` streams rows; the test fixture's data is
        # already in memory, so we just iterate. `chunk_size` is ignored intentionally.
        return iter(self._rows)


class _FakeBulkDeleteQuerySet:
    """Returned by `_FakeManager.filter(pk__in=...)` so the helper can emit a single
    bulk `.delete()` for orphan rows."""

    def __init__(self, manager, pks):
        self._manager = manager
        self._pks = list(pks)

    def delete(self):
        pk_set = set(self._pks)
        for pk in self._pks:
            self._manager.delete_log.append(pk)
        self._manager._rows = [r for r in self._manager._rows if r.pk not in pk_set]


class _FakeValueList(list):
    def distinct(self):
        seen = []
        for row in self:
            if row not in seen:
                seen.append(row)
        return seen


class _FakeFlatList(list):
    def distinct(self):
        seen = []
        for row in self:
            if row not in seen:
                seen.append(row)
        return seen


class _FakeUpdateDeleteQuerySet:
    def __init__(self, manager, pk):
        self._manager = manager
        self._pk = pk

    def update(self, **kwargs):
        self._manager.update_log.append((self._pk, kwargs))
        for row in self._manager._rows:
            if getattr(row, "pk", None) == self._pk:
                for k, v in kwargs.items():
                    setattr(row, k, v)
                break

    def delete(self):
        self._manager.delete_log.append(self._pk)
        self._manager._rows = [r for r in self._manager._rows if getattr(r, "pk", None) != self._pk]


class _FakeManager:
    def __init__(self, rows):
        self._rows = list(rows)
        self.update_log = []
        self.delete_log = []
        self.using_log = []
        # Each element is a list of (pk, fields_dict) tuples — one entry per
        # `bulk_update` flush, so tests can assert chunking behavior.
        self.bulk_update_batches = []

    def using(self, alias):
        self.using_log.append(alias)
        return self

    def all(self):
        return _FakeQuerySet(self._rows).all()

    def values(self, *fields):
        return _FakeQuerySet(self._rows).values(*fields)

    def values_list(self, *fields, flat=False):
        return _FakeQuerySet(self._rows).values_list(*fields, flat=flat)

    def filter(self, **kwargs):
        if "pk" in kwargs:
            return _FakeUpdateDeleteQuerySet(self, kwargs["pk"])
        if "pk__in" in kwargs:
            return _FakeBulkDeleteQuerySet(self, kwargs["pk__in"])
        return _FakeQuerySet(self._rows).filter(**kwargs)

    def exclude(self, **kwargs):
        return _FakeQuerySet(self._rows).exclude(**kwargs)

    def bulk_update(self, instances, fields, batch_size=None):
        # Mirror Django: write a single `UPDATE … CASE WHEN` per `batch_size`
        # group. The fixture records each batch (and replays the field writes onto
        # the underlying rows so subsequent reads see the new values) and ALSO
        # appends per-row entries to `update_log` in the legacy `(pk, kwargs)`
        # shape so the older tests that pre-date the bulk path keep passing.
        instances = list(instances)
        bs = batch_size or len(instances) or 1
        for start in range(0, len(instances), bs):
            chunk = instances[start : start + bs]
            batch_entries = []
            chunk_by_pk = {inst.pk: inst for inst in chunk}
            for inst in chunk:
                kwargs = {f: getattr(inst, f) for f in fields}
                batch_entries.append((inst.pk, kwargs))
                self.update_log.append((inst.pk, kwargs))
            self.bulk_update_batches.append(batch_entries)
            for row in self._rows:
                src = chunk_by_pk.get(row.pk)
                if src is None:
                    continue
                for field in fields:
                    setattr(row, field, getattr(src, field))


class _FollowLegacyFactory(factory.Factory):
    class Meta:
        model = SimpleNamespace

    pk = factory.Sequence(lambda n: n + 1)
    actor_id = 0
    target_id = 0


class _DocumentIdRowFactory(factory.Factory):
    class Meta:
        model = SimpleNamespace

    id = 1000
    content_type_id = 99
    object_id = 1


def _make_apps(*, follows, documents, profile_ct_id=99):
    follow_manager = _FakeManager(follows)
    document_manager = _FakeManager(documents)

    class _ContentTypeManager:
        def __init__(self):
            self.using_log = []

        def using(self, alias):
            self.using_log.append(alias)
            return self

        def _row(self):
            return SimpleNamespace(id=profile_ct_id, app_label="profiles", model="profile")

        def get_or_create(self, **kwargs):
            assert kwargs == {"app_label": "profiles", "model": "profile"}
            return self._row(), False

        def filter(self, **kwargs):
            assert kwargs == {"app_label": "profiles", "model": "profile"}
            row = self._row()

            class _Filtered:
                def first(_self):
                    return row

            return _Filtered()

    follow_model = SimpleNamespace(objects=follow_manager)
    profile_model = SimpleNamespace(
        _meta=SimpleNamespace(app_label="profiles", model_name="profile")
    )
    documentid_model = SimpleNamespace(objects=document_manager)
    contenttype_model = SimpleNamespace(objects=_ContentTypeManager())

    class FakeApps:
        def get_model(self, app_label, model_name):
            mapping = {
                ("baseapp_follows", "Follow"): follow_model,
                ("profiles", "Profile"): profile_model,
                ("baseapp_core", "DocumentId"): documentid_model,
                ("contenttypes", "ContentType"): contenttype_model,
            }
            return mapping[(app_label, model_name)]

    return FakeApps(), follow_manager, document_manager


@pytest.fixture(autouse=True)
def _stub_swapper_is_not_swapped():
    """`get_apps_model` consults `swapper.is_swapped` for the registered model. Force the
    "not swapped" branch so the helper resolves through `apps.get_model` with the labels
    we control in the fake apps registry."""
    with patch(
        "baseapp_follows.migration_helpers.convert_follow_profile_fks_into_document_id_helper.get_apps_model",
        side_effect=lambda apps, app_label, model_name: apps.get_model(app_label, model_name),
    ):
        yield


def test_migrate_follow_profile_fks_to_document_id_remaps_actor_and_target():
    follows = [
        _FollowLegacyFactory(pk=1, actor_id=10, target_id=20),
        _FollowLegacyFactory(pk=2, actor_id=20, target_id=30),
    ]
    documents = [
        _DocumentIdRowFactory(id=100, content_type_id=99, object_id=10),
        _DocumentIdRowFactory(id=200, content_type_id=99, object_id=20),
        _DocumentIdRowFactory(id=300, content_type_id=99, object_id=30),
    ]
    apps, follow_manager, _ = _make_apps(follows=follows, documents=documents)

    # Mock get_model("profiles", "Profile") inside Profile lookup as well — the helper
    # passes source_app_label="profiles" by default, so use that label here.
    migrate_follow_profile_fks_to_document_id(
        apps,
        schema_editor=None,
        source_app_label="profiles",
        source_model_name="Profile",
    )

    assert follow_manager.update_log == [
        (1, {"actor_id": 100, "target_id": 200}),
        (2, {"actor_id": 200, "target_id": 300}),
    ]
    assert follow_manager.delete_log == []


def test_migrate_follow_profile_fks_deletes_orphaned_rows_when_no_documentid_match():
    follows = [
        _FollowLegacyFactory(pk=1, actor_id=10, target_id=20),
        _FollowLegacyFactory(pk=2, actor_id=999, target_id=20),  # actor missing doc
    ]
    documents = [
        _DocumentIdRowFactory(id=100, content_type_id=99, object_id=10),
        _DocumentIdRowFactory(id=200, content_type_id=99, object_id=20),
    ]
    apps, follow_manager, _ = _make_apps(follows=follows, documents=documents)

    migrate_follow_profile_fks_to_document_id(
        apps,
        schema_editor=None,
        source_app_label="profiles",
        source_model_name="Profile",
    )

    assert follow_manager.update_log == [(1, {"actor_id": 100, "target_id": 200})]
    assert follow_manager.delete_log == [2]


def test_assert_all_follow_rows_reference_document_ids_passes_when_all_valid():
    follows = [_FollowLegacyFactory(pk=1, actor_id=100, target_id=200)]
    documents = [
        _DocumentIdRowFactory(id=100, content_type_id=99, object_id=10),
        _DocumentIdRowFactory(id=200, content_type_id=99, object_id=20),
    ]
    apps, _, _ = _make_apps(follows=follows, documents=documents)

    assert_all_follow_rows_reference_document_ids(apps, schema_editor=None)


def test_assert_all_follow_rows_reference_document_ids_raises_when_dangling():
    follows = [_FollowLegacyFactory(pk=1, actor_id=100, target_id=999)]
    documents = [_DocumentIdRowFactory(id=100, content_type_id=99, object_id=10)]
    apps, _, _ = _make_apps(follows=follows, documents=documents)

    with pytest.raises(ValueError, match="1 row\\(s\\) still reference"):
        assert_all_follow_rows_reference_document_ids(apps, schema_editor=None)


def test_assert_uses_db_alias_from_schema_editor():
    follows = [_FollowLegacyFactory(pk=1, actor_id=100, target_id=200)]
    documents = [
        _DocumentIdRowFactory(id=100, content_type_id=99, object_id=10),
        _DocumentIdRowFactory(id=200, content_type_id=99, object_id=20),
    ]
    apps, _, _ = _make_apps(follows=follows, documents=documents)
    se = SimpleNamespace(connection=SimpleNamespace(alias="replica"))

    assert_all_follow_rows_reference_document_ids(apps, schema_editor=se)


def test_reverse_migrate_follow_document_id_fks_to_profile_restores_profile_pks():
    follows = [
        _FollowLegacyFactory(pk=1, actor_id=100, target_id=200),
        _FollowLegacyFactory(pk=2, actor_id=200, target_id=300),
    ]
    documents = [
        _DocumentIdRowFactory(id=100, content_type_id=99, object_id=10),
        _DocumentIdRowFactory(id=200, content_type_id=99, object_id=20),
        _DocumentIdRowFactory(id=300, content_type_id=99, object_id=30),
    ]
    apps, follow_manager, _ = _make_apps(follows=follows, documents=documents)

    reverse_migrate_follow_document_id_fks_to_profile(
        apps,
        schema_editor=None,
        source_app_label="profiles",
        source_model_name="Profile",
    )

    assert follow_manager.update_log == [
        (1, {"actor_id": 10, "target_id": 20}),
        (2, {"actor_id": 20, "target_id": 30}),
    ]


def test_reverse_migrate_follow_document_id_fks_skips_unknown_documents():
    follows = [_FollowLegacyFactory(pk=1, actor_id=100, target_id=999)]
    documents = [_DocumentIdRowFactory(id=100, content_type_id=99, object_id=10)]
    apps, follow_manager, _ = _make_apps(follows=follows, documents=documents)

    reverse_migrate_follow_document_id_fks_to_profile(
        apps,
        schema_editor=None,
        source_app_label="profiles",
        source_model_name="Profile",
    )

    assert follow_manager.update_log == []


def test_migrate_uses_db_alias_from_schema_editor():
    """Every ORM access in the forward migration must be pinned to the schema editor's
    alias, so reads (ContentType / DocumentId / Follow lookups) and writes
    (Follow.update / .delete) hit the same database when running against a non-default
    connection. The assert helper at the end of `migrate_*` re-pins, so each manager
    records the alias more than once — what matters is that nothing leaks to the
    default connection (i.e. no `None` / unpinned entries)."""
    follows = [_FollowLegacyFactory(pk=1, actor_id=10, target_id=20)]
    documents = [
        _DocumentIdRowFactory(id=100, content_type_id=99, object_id=10),
        _DocumentIdRowFactory(id=200, content_type_id=99, object_id=20),
    ]
    apps, follow_manager, document_manager = _make_apps(follows=follows, documents=documents)
    ct_manager = apps.get_model("contenttypes", "ContentType").objects
    se = SimpleNamespace(connection=SimpleNamespace(alias="replica"))

    migrate_follow_profile_fks_to_document_id(
        apps,
        schema_editor=se,
        source_app_label="profiles",
        source_model_name="Profile",
    )

    assert follow_manager.using_log and all(a == "replica" for a in follow_manager.using_log)
    assert document_manager.using_log and all(a == "replica" for a in document_manager.using_log)
    assert ct_manager.using_log == ["replica"]


def test_reverse_migrate_uses_db_alias_from_schema_editor():
    follows = [_FollowLegacyFactory(pk=1, actor_id=100, target_id=200)]
    documents = [
        _DocumentIdRowFactory(id=100, content_type_id=99, object_id=10),
        _DocumentIdRowFactory(id=200, content_type_id=99, object_id=20),
    ]
    apps, follow_manager, document_manager = _make_apps(follows=follows, documents=documents)
    ct_manager = apps.get_model("contenttypes", "ContentType").objects
    se = SimpleNamespace(connection=SimpleNamespace(alias="replica"))

    reverse_migrate_follow_document_id_fks_to_profile(
        apps,
        schema_editor=se,
        source_app_label="profiles",
        source_model_name="Profile",
    )

    assert follow_manager.using_log == ["replica"]
    assert document_manager.using_log == ["replica"]
    assert ct_manager.using_log == ["replica"]


def test_migrate_streams_and_bulk_updates_in_chunks(monkeypatch):
    """Forward migration should flush via `bulk_update` once per chunk and emit a
    single `filter(pk__in=…).delete()` for all orphans, regardless of the row count
    on the table. This is the regression we want to lock in for projects with 1M+
    follow rows where per-row UPDATE/DELETE is unworkable."""
    from baseapp_follows.migration_helpers import (
        convert_follow_profile_fks_into_document_id_helper as helper,
    )

    # Force a tiny chunk so we can exercise multi-batch flushing without inflating
    # the test fixture.
    monkeypatch.setattr(helper, "_CHUNK_SIZE", 3)

    documents = [
        _DocumentIdRowFactory(id=1000 + i, content_type_id=99, object_id=i) for i in range(1, 8)
    ]
    follows = [_FollowLegacyFactory(pk=i, actor_id=i, target_id=i) for i in range(1, 8)]
    # Two orphan rows referencing object_ids that have no DocumentId.
    follows.append(_FollowLegacyFactory(pk=901, actor_id=99999, target_id=1))
    follows.append(_FollowLegacyFactory(pk=902, actor_id=2, target_id=99999))
    apps, follow_manager, _ = _make_apps(follows=follows, documents=documents)

    migrate_follow_profile_fks_to_document_id(
        apps,
        schema_editor=None,
        source_app_label="profiles",
        source_model_name="Profile",
    )

    # 7 survivors flushed at chunk size 3 → batches of 3, 3, 1.
    batch_sizes = [len(b) for b in follow_manager.bulk_update_batches]
    assert batch_sizes == [3, 3, 1], batch_sizes
    # No batch ever exceeds the configured chunk size.
    assert all(size <= 3 for size in batch_sizes)
    # All survivors got the right doc-id mapping in their batched UPDATE.
    flat = [entry for batch in follow_manager.bulk_update_batches for entry in batch]
    assert flat == [(i, {"actor_id": 1000 + i, "target_id": 1000 + i}) for i in range(1, 8)]
    # Orphans collected and removed in ONE delete call (both PKs in the same call).
    assert follow_manager.delete_log == [901, 902]


def test_reverse_migrate_streams_and_bulk_updates_in_chunks(monkeypatch):
    from baseapp_follows.migration_helpers import (
        convert_follow_profile_fks_into_document_id_helper as helper,
    )

    monkeypatch.setattr(helper, "_CHUNK_SIZE", 2)

    documents = [
        _DocumentIdRowFactory(id=1000 + i, content_type_id=99, object_id=i) for i in range(1, 6)
    ]
    follows = [
        _FollowLegacyFactory(pk=i, actor_id=1000 + i, target_id=1000 + i) for i in range(1, 6)
    ]
    apps, follow_manager, _ = _make_apps(follows=follows, documents=documents)

    reverse_migrate_follow_document_id_fks_to_profile(
        apps,
        schema_editor=None,
        source_app_label="profiles",
        source_model_name="Profile",
    )

    # 5 rows at chunk size 2 → batches of 2, 2, 1.
    assert [len(b) for b in follow_manager.bulk_update_batches] == [2, 2, 1]
    # Reverse path never deletes anything.
    assert follow_manager.delete_log == []
