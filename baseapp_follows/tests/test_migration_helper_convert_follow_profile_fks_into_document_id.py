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

    def using(self, _alias):
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
        return _FakeQuerySet(self._rows).filter(**kwargs)

    def exclude(self, **kwargs):
        return _FakeQuerySet(self._rows).exclude(**kwargs)


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
        def get(self, **kwargs):
            assert kwargs == {"app_label": "profiles", "model": "profile"}
            return SimpleNamespace(id=profile_ct_id, app_label="profiles", model="profile")

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
