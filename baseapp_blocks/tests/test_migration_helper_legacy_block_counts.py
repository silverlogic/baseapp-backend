from types import SimpleNamespace

import factory

from baseapp_blocks.migration_helpers.convert_legacy_block_counts_to_metadata_helper import (
    migrate_legacy_block_counts_to_metadata,
    reverse_migrate_legacy_block_counts_from_metadata,
)


class _ModelRowFactory(factory.Factory):
    class Meta:
        model = SimpleNamespace

    pk = factory.Sequence(lambda n: n + 1)
    blockers_count = 0
    blocking_count = 0


class _ContentTypeRowFactory(factory.Factory):
    class Meta:
        model = SimpleNamespace

    id = 77
    app_label = "profiles"
    model = "profile"


class _DocumentRowFactory(factory.Factory):
    class Meta:
        model = SimpleNamespace

    id = 1001
    content_type_id = 77
    object_id = 1


class _LegacyQuerySet:
    """Minimal queryset shim — the helper calls `only()`, `exists()`, iteration."""

    def __init__(self, rows):
        self._rows = list(rows)

    def only(self, *_args):
        return self

    def exists(self):
        return bool(self._rows)

    def __iter__(self):
        return iter(self._rows)


class _UpdateQuerySet:
    def __init__(self, log, pk):
        self._log = log
        self._pk = pk

    def update(self, **kwargs):
        self._log.append((self._pk, kwargs))


class _SourceManager:
    def __init__(self, rows):
        self._rows = rows
        self.update_log = []

    def only(self, *_args):
        return _LegacyQuerySet(self._rows)

    def filter(self, **kwargs):
        if "pk" in kwargs:
            return _UpdateQuerySet(self.update_log, kwargs["pk"])
        raise AssertionError("Unexpected filter call")


def _make_apps(*, source_model, content_type, get_or_create_log, metadata_log):
    class ContentTypeManager:
        def get_or_create(self, **kwargs):
            assert kwargs == {
                "app_label": source_model._meta.app_label,
                "model": source_model._meta.model_name,
            }
            return content_type, False

        def filter(self, **kwargs):
            assert kwargs == {
                "app_label": source_model._meta.app_label,
                "model": source_model._meta.model_name,
            }

            class _Filtered:
                def first(_self):
                    return content_type

            return _Filtered()

    class DocumentIdManager:
        def get_or_create(self, **kwargs):
            doc = _DocumentRowFactory(
                id=1000 + kwargs["object_id"],
                content_type_id=kwargs["content_type_id"],
                object_id=kwargs["object_id"],
            )
            get_or_create_log.append(kwargs)
            return doc, True

    class BlockableMetadataManager:
        def update_or_create(self, **kwargs):
            metadata_log.append(kwargs)
            return SimpleNamespace(), True

    class FakeApps:
        def get_model(self, app_label, model_name):
            mapping = {
                ("profiles", "Profile"): source_model,
                ("contenttypes", "ContentType"): SimpleNamespace(objects=ContentTypeManager()),
                ("baseapp_core", "DocumentId"): SimpleNamespace(objects=DocumentIdManager()),
                ("baseapp_blocks", "BlockableMetadata"): SimpleNamespace(
                    objects=BlockableMetadataManager()
                ),
            }
            return mapping[(app_label, model_name)]

    return FakeApps()


def test_migrate_legacy_block_counts_to_metadata_creates_metadata_rows():
    source_rows = [
        _ModelRowFactory(pk=1, blockers_count=3, blocking_count=2),
        _ModelRowFactory(pk=2, blockers_count=0, blocking_count=5),
    ]
    source_model = SimpleNamespace(
        _meta=SimpleNamespace(app_label="profiles", model_name="profile"),
        objects=_SourceManager(source_rows),
    )
    ct = _ContentTypeRowFactory(id=77, app_label="profiles", model="profile")
    created_docs = []
    metadata_updates = []

    apps = _make_apps(
        source_model=source_model,
        content_type=ct,
        get_or_create_log=created_docs,
        metadata_log=metadata_updates,
    )

    migrate_legacy_block_counts_to_metadata(
        apps,
        schema_editor=None,
        source_app_label="profiles",
        source_model_name="Profile",
    )

    assert created_docs == [
        {"content_type_id": 77, "object_id": 1},
        {"content_type_id": 77, "object_id": 2},
    ]
    assert metadata_updates == [
        {"target_id": 1001, "defaults": {"blockers_count": 3, "blocking_count": 2}},
        {"target_id": 1002, "defaults": {"blockers_count": 0, "blocking_count": 5}},
    ]


def test_migrate_legacy_block_counts_no_op_when_no_source_rows():
    """Empty source table → helper creates no DocumentId or metadata rows.
    Bails before touching ContentType so it's safe on a fresh test DB where
    ``post_migrate`` hasn't yet populated the row."""
    source_model = SimpleNamespace(
        _meta=SimpleNamespace(app_label="profiles", model_name="profile"),
        objects=_SourceManager([]),
    )
    ct = _ContentTypeRowFactory(id=77, app_label="profiles", model="profile")
    created_docs = []
    metadata_updates = []

    apps = _make_apps(
        source_model=source_model,
        content_type=ct,
        get_or_create_log=created_docs,
        metadata_log=metadata_updates,
    )

    migrate_legacy_block_counts_to_metadata(
        apps,
        schema_editor=None,
        source_app_label="profiles",
        source_model_name="Profile",
    )

    assert created_docs == []
    assert metadata_updates == []


def test_reverse_migrate_legacy_block_counts_restores_source_fields():
    source_model = SimpleNamespace(
        _meta=SimpleNamespace(app_label="profiles", model_name="profile"),
        objects=_SourceManager([]),
    )
    ct = _ContentTypeRowFactory(id=77, app_label="profiles", model="profile")
    metadata_rows = [
        SimpleNamespace(
            blockers_count=4,
            blocking_count=7,
            target=SimpleNamespace(object_id=10),
        )
    ]

    class _MetadataQuerySet:
        def __init__(self, rows):
            self._rows = rows

        def select_related(self, *_args):
            return self

        def __iter__(self):
            return iter(self._rows)

    class ContentTypeManager:
        def filter(self, **kwargs):
            assert kwargs == {"app_label": "profiles", "model": "profile"}

            class _Filtered:
                def first(_self):
                    return ct

            return _Filtered()

    class MetadataManager:
        def filter(self, **kwargs):
            assert kwargs == {"target__content_type_id": 77}
            return _MetadataQuerySet(metadata_rows)

    class FakeApps:
        def get_model(self, app_label, model_name):
            mapping = {
                ("profiles", "Profile"): source_model,
                ("contenttypes", "ContentType"): SimpleNamespace(objects=ContentTypeManager()),
                ("baseapp_blocks", "BlockableMetadata"): SimpleNamespace(objects=MetadataManager()),
            }
            return mapping[(app_label, model_name)]

    reverse_migrate_legacy_block_counts_from_metadata(
        FakeApps(),
        schema_editor=None,
        source_app_label="profiles",
        source_model_name="Profile",
    )

    assert source_model.objects.update_log == [(10, {"blockers_count": 4, "blocking_count": 7})]


def test_reverse_migrate_legacy_block_counts_no_op_when_content_type_missing():
    source_model = SimpleNamespace(
        _meta=SimpleNamespace(app_label="profiles", model_name="profile"),
        objects=_SourceManager([]),
    )

    class ContentTypeManager:
        def filter(self, **_kwargs):
            class _Filtered:
                def first(_self):
                    return None

            return _Filtered()

    class MetadataManager:
        def filter(self, **kwargs):
            raise AssertionError("Should not query metadata when ContentType is missing")

    class FakeApps:
        def get_model(self, app_label, model_name):
            mapping = {
                ("profiles", "Profile"): source_model,
                ("contenttypes", "ContentType"): SimpleNamespace(objects=ContentTypeManager()),
                ("baseapp_blocks", "BlockableMetadata"): SimpleNamespace(objects=MetadataManager()),
            }
            return mapping[(app_label, model_name)]

    reverse_migrate_legacy_block_counts_from_metadata(
        FakeApps(),
        schema_editor=None,
        source_app_label="profiles",
        source_model_name="Profile",
    )

    assert source_model.objects.update_log == []
