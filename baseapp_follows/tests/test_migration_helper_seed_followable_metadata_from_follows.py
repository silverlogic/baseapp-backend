from types import SimpleNamespace
from unittest.mock import patch

import factory
import pytest

from baseapp_follows.migration_helpers.seed_followable_metadata_from_follows_helper import (
    reverse_seed_followable_metadata,
    seed_followable_metadata_from_follows,
)


class _FakeFlatList(list):
    def distinct(self):
        seen = []
        for row in self:
            if row not in seen:
                seen.append(row)
        return seen


class _FakeQuerySet:
    def __init__(self, rows):
        self._rows = list(rows)

    def filter(self, **kwargs):
        rows = self._rows
        for key, value in kwargs.items():
            if key.endswith("__in"):
                field = key.replace("__in", "")
                rows = [r for r in rows if getattr(r, field) in value]
            else:
                rows = [r for r in rows if getattr(r, key) == value]
        return _FakeQuerySet(rows)

    def values_list(self, *fields, flat=False):
        if flat:
            assert len(fields) == 1
            return _FakeFlatList([getattr(r, fields[0]) for r in self._rows])
        return [tuple(getattr(r, f) for f in fields) for r in self._rows]

    def count(self):
        return len(self._rows)

    def delete(self):
        deleted = list(self._rows)
        self._rows.clear()
        return deleted


class _FakeFollowManager:
    def __init__(self, rows):
        self._rows = list(rows)
        self.using_log = []

    def using(self, alias):
        self.using_log.append(alias)
        return self

    def filter(self, **kwargs):
        return _FakeQuerySet(self._rows).filter(**kwargs)

    def values_list(self, *fields, flat=False):
        return _FakeQuerySet(self._rows).values_list(*fields, flat=flat)


class _FakeMetadataManager:
    def __init__(self, rows=None):
        self._rows = list(rows or [])
        self.update_log = []
        self.delete_log = []
        self.using_log = []

    def using(self, alias):
        self.using_log.append(alias)
        return self

    def update_or_create(self, **kwargs):
        self.update_log.append(kwargs)
        return SimpleNamespace(), True

    def filter(self, **kwargs):
        manager = self

        class _DeleteQS:
            def __init__(self, rows):
                self._rows = rows

            def delete(self):
                manager.delete_log.append(kwargs)
                manager._rows = [r for r in manager._rows if r not in self._rows]

        rows = manager._rows
        for key, value in kwargs.items():
            if key.endswith("__in"):
                field = key.replace("__in", "")
                rows = [r for r in rows if getattr(r, field) in value]
            else:
                rows = [r for r in rows if getattr(r, key) == value]
        return _DeleteQS(rows)


class _FollowFactory(factory.Factory):
    class Meta:
        model = SimpleNamespace

    pk = factory.Sequence(lambda n: n + 1)
    actor_id = 0
    target_id = 0


def _make_apps(*, follows, metadata_rows=None):
    follow_manager = _FakeFollowManager(follows)
    metadata_manager = _FakeMetadataManager(metadata_rows or [])

    follow_model = SimpleNamespace(objects=follow_manager)
    metadata_model = SimpleNamespace(objects=metadata_manager)

    class FakeApps:
        def get_model(self, app_label, model_name):
            mapping = {
                ("baseapp_follows", "Follow"): follow_model,
                ("baseapp_follows", "FollowableMetadata"): metadata_model,
            }
            return mapping[(app_label, model_name)]

    return FakeApps(), follow_manager, metadata_manager


@pytest.fixture(autouse=True)
def _stub_swapper_is_not_swapped():
    """Force the helper through `apps.get_model` instead of `swapper.load_model`."""
    with patch(
        "baseapp_follows.migration_helpers.seed_followable_metadata_from_follows_helper.get_apps_model",
        side_effect=lambda apps, app_label, model_name: apps.get_model(app_label, model_name),
    ):
        yield


def test_seed_followable_metadata_creates_one_row_per_unique_documentid():
    follows = [
        _FollowFactory(pk=1, actor_id=100, target_id=200),
        _FollowFactory(pk=2, actor_id=100, target_id=300),
        _FollowFactory(pk=3, actor_id=200, target_id=300),
    ]
    apps, _, metadata_manager = _make_apps(follows=follows)

    seed_followable_metadata_from_follows(apps, schema_editor=None)

    # 100 follows {200, 300} → following_count=2, followers_count=0
    # 200 follows {300} → following_count=1, followers_count=1 (followed by 100)
    # 300 follows nothing → following_count=0, followers_count=2 (followed by 100, 200)
    by_target = {entry["target_id"]: entry["defaults"] for entry in metadata_manager.update_log}
    assert by_target[100] == {"followers_count": 0, "following_count": 2}
    assert by_target[200] == {"followers_count": 1, "following_count": 1}
    assert by_target[300] == {"followers_count": 2, "following_count": 0}


def test_seed_followable_metadata_no_op_when_no_follows():
    apps, _, metadata_manager = _make_apps(follows=[])

    seed_followable_metadata_from_follows(apps, schema_editor=None)

    assert metadata_manager.update_log == []


def test_reverse_seed_followable_metadata_deletes_metadata_for_known_doc_ids():
    follows = [_FollowFactory(pk=1, actor_id=100, target_id=200)]
    apps, _, metadata_manager = _make_apps(
        follows=follows,
        metadata_rows=[
            SimpleNamespace(target_id=100),
            SimpleNamespace(target_id=200),
            # Unrelated metadata row, must NOT be deleted
            SimpleNamespace(target_id=999),
        ],
    )

    reverse_seed_followable_metadata(apps, schema_editor=None)

    # The delete filter received target_id__in={100, 200} (order is set-iteration)
    assert len(metadata_manager.delete_log) == 1
    deleted_kwargs = metadata_manager.delete_log[0]
    assert set(deleted_kwargs["target_id__in"]) == {100, 200}
    # 999 untouched
    assert any(r.target_id == 999 for r in metadata_manager._rows)


def test_reverse_seed_followable_metadata_no_op_when_no_follows():
    apps, _, metadata_manager = _make_apps(follows=[])

    reverse_seed_followable_metadata(apps, schema_editor=None)

    assert metadata_manager.delete_log == []


def test_seed_uses_db_alias_from_schema_editor():
    """Both Follow reads (values_list / filter / count) and FollowableMetadata writes
    (update_or_create) must be pinned to schema_editor.connection.alias so reads and
    writes never split across databases on a multi-db migration run."""
    follows = [_FollowFactory(pk=1, actor_id=100, target_id=200)]
    apps, follow_manager, metadata_manager = _make_apps(follows=follows)
    se = SimpleNamespace(connection=SimpleNamespace(alias="replica"))

    seed_followable_metadata_from_follows(apps, schema_editor=se)

    assert follow_manager.using_log and all(a == "replica" for a in follow_manager.using_log)
    assert metadata_manager.using_log == ["replica"]


def test_reverse_seed_uses_db_alias_from_schema_editor():
    follows = [_FollowFactory(pk=1, actor_id=100, target_id=200)]
    apps, follow_manager, metadata_manager = _make_apps(
        follows=follows,
        metadata_rows=[SimpleNamespace(target_id=100), SimpleNamespace(target_id=200)],
    )
    se = SimpleNamespace(connection=SimpleNamespace(alias="replica"))

    reverse_seed_followable_metadata(apps, schema_editor=se)

    assert follow_manager.using_log and all(a == "replica" for a in follow_manager.using_log)
    assert metadata_manager.using_log == ["replica"]
