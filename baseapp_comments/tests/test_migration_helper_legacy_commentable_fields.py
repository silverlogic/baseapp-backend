from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any

import factory

from baseapp_comments.migration_helpers.convert_legacy_commentable_fields_into_metadata_helper import (
    migrate_legacy_commentable_fields_to_metadata,
    reverse_migrate_legacy_commentable_fields_from_metadata,
)


class _ModelRowFactory(factory.Factory):
    class Meta:
        model = SimpleNamespace

    pk = factory.Sequence(lambda n: n + 1)
    comments_count = {"total": 0, "main": 0, "replies": 0, "pinned": 0, "reported": 0}
    is_comments_enabled = True


class _ContentTypeRowFactory(factory.Factory):
    class Meta:
        model = SimpleNamespace

    id = 77
    app_label = "pages"
    model = "page"


class _DocumentRowFactory(factory.Factory):
    class Meta:
        model = SimpleNamespace

    id = 1001
    content_type_id = 77
    object_id = 1


class _LegacyQuerySet:
    def __init__(self, rows) -> None:
        self._rows = list(rows)

    def exclude(self, **kwargs) -> "_LegacyQuerySet":
        rows = self._rows
        for key, value in kwargs.items():
            if key.endswith("__isnull"):
                field = key.replace("__isnull", "")
                rows = [r for r in rows if (getattr(r, field) is None) != value]
            else:
                rows = [r for r in rows if getattr(r, key) != value]
        return _LegacyQuerySet(rows)

    def only(self, *_args) -> "_LegacyQuerySet":
        return self

    def __iter__(self) -> Iterator[SimpleNamespace]:
        return iter(self._rows)


class _UpdateQuerySet:
    def __init__(self, log, pk) -> None:
        self._log = log
        self._pk = pk

    def update(self, **kwargs) -> None:
        self._log.append((self._pk, kwargs))


class _SourceManager:
    def __init__(self, rows) -> None:
        self._rows = rows
        self.update_log = []

    def exclude(self, **kwargs) -> _LegacyQuerySet:
        return _LegacyQuerySet(self._rows).exclude(**kwargs)

    def filter(self, **kwargs) -> _UpdateQuerySet:
        if "pk" in kwargs:
            return _UpdateQuerySet(self.update_log, kwargs["pk"])
        raise AssertionError("Unexpected filter call")


def test_migrate_legacy_commentable_fields_to_metadata_creates_metadata_rows() -> None:
    source_rows = [
        _ModelRowFactory(
            pk=1,
            comments_count={"total": 3, "main": 2, "replies": 1, "pinned": 0, "reported": 0},
            is_comments_enabled=False,
        ),
        _ModelRowFactory(
            pk=2,
            comments_count={"total": 1, "main": 1, "replies": 0, "pinned": 0, "reported": 0},
            is_comments_enabled=True,
        ),
    ]

    source_model = SimpleNamespace(
        _meta=SimpleNamespace(app_label="pages", model_name="page"),
        objects=_SourceManager(source_rows),
    )

    ct = _ContentTypeRowFactory(id=77, app_label="pages", model="page")
    created_docs = []
    metadata_updates = []

    class ContentTypeManager:
        def get_or_create(self, **kwargs) -> tuple[SimpleNamespace, bool]:
            assert kwargs == {"app_label": "pages", "model": "page"}
            return ct, False

    class DocumentIdManager:
        def get_or_create(self, **kwargs) -> tuple[SimpleNamespace, bool]:
            doc = _DocumentRowFactory(
                id=1000 + kwargs["object_id"],
                content_type_id=kwargs["content_type_id"],
                object_id=kwargs["object_id"],
            )
            created_docs.append(kwargs)
            return doc, True

    class CommentableMetadataManager:
        def update_or_create(self, **kwargs) -> tuple[SimpleNamespace, bool]:
            metadata_updates.append(kwargs)
            return SimpleNamespace(), True

    class FakeApps:
        def get_model(self, app_label, model_name) -> SimpleNamespace:
            mapping = {
                ("pages", "Page"): source_model,
                ("contenttypes", "ContentType"): SimpleNamespace(objects=ContentTypeManager()),
                ("baseapp_core", "DocumentId"): SimpleNamespace(objects=DocumentIdManager()),
                ("comments", "CommentableMetadata"): SimpleNamespace(
                    objects=CommentableMetadataManager()
                ),
            }
            return mapping[(app_label, model_name)]

    migrate_legacy_commentable_fields_to_metadata(
        FakeApps(),
        schema_editor=None,
        source_app_label="pages",
        source_model_name="Page",
    )

    assert created_docs == [
        {"content_type_id": 77, "object_id": 1},
        {"content_type_id": 77, "object_id": 2},
    ]
    assert metadata_updates == [
        {
            "target_id": 1001,
            "defaults": {
                "comments_count": {"total": 3, "main": 2, "replies": 1, "pinned": 0, "reported": 0},
                "is_comments_enabled": False,
            },
        },
        {
            "target_id": 1002,
            "defaults": {
                "comments_count": {"total": 1, "main": 1, "replies": 0, "pinned": 0, "reported": 0},
                "is_comments_enabled": True,
            },
        },
    ]


def test_reverse_migrate_legacy_commentable_fields_from_metadata_restores_source_fields() -> None:
    source_model = SimpleNamespace(
        _meta=SimpleNamespace(app_label="pages", model_name="page"),
        objects=_SourceManager([]),
    )
    ct = _ContentTypeRowFactory(id=77, app_label="pages", model="page")
    metadata_rows = [
        SimpleNamespace(
            comments_count={"total": 7, "main": 5, "replies": 2, "pinned": 0, "reported": 0},
            is_comments_enabled=False,
            target=SimpleNamespace(object_id=10),
        )
    ]

    class _MetadataQuerySet:
        def __init__(self, rows) -> None:
            self._rows = rows

        def select_related(self, *_args) -> "_MetadataQuerySet":
            return self

        def __iter__(self) -> Iterator[SimpleNamespace]:
            return iter(self._rows)

    class ContentTypeManager:
        def filter(self, **kwargs) -> Any:
            assert kwargs == {"app_label": "pages", "model": "page"}

            class _Filtered:
                def first(_self) -> SimpleNamespace:
                    return ct

            return _Filtered()

    class MetadataManager:
        def filter(self, **kwargs) -> "_MetadataQuerySet":
            assert kwargs == {"target__content_type_id": 77}
            return _MetadataQuerySet(metadata_rows)

    class FakeApps:
        def get_model(self, app_label, model_name) -> SimpleNamespace:
            mapping = {
                ("pages", "Page"): source_model,
                ("contenttypes", "ContentType"): SimpleNamespace(objects=ContentTypeManager()),
                ("comments", "CommentableMetadata"): SimpleNamespace(objects=MetadataManager()),
            }
            return mapping[(app_label, model_name)]

    reverse_migrate_legacy_commentable_fields_from_metadata(
        FakeApps(),
        schema_editor=None,
        source_app_label="pages",
        source_model_name="Page",
    )

    assert source_model.objects.update_log == [
        (
            10,
            {
                "comments_count": {"total": 7, "main": 5, "replies": 2, "pinned": 0, "reported": 0},
                "is_comments_enabled": False,
            },
        )
    ]


# ---------------------------------------------------------------------------
# Multi-db: schema_editor.connection.alias must be honored end-to-end so reads
# (source model + ContentType + DocumentId) and writes (CommentableMetadata
# upserts on forward, source updates on reverse) all hit the same database.
# ---------------------------------------------------------------------------


def _alias_tracking_apps(
    *, source_rows, ct, source_meta=("pages", "page")
) -> tuple[Any, Any, Any, Any, Any]:
    """Build a FakeApps where every manager records its `.using(alias)` calls in a
    `using_log`. Returns (apps, source_manager, ct_manager, doc_manager, metadata_manager)
    so the test can assert every layer was pinned to the alias."""
    source_app_label, source_model_name = source_meta

    class _AliasManager:
        def __init__(self) -> None:
            self.using_log = []

        def using(self, alias) -> "_AliasManager":
            self.using_log.append(alias)
            return self

    class SourceManager(_AliasManager):
        def __init__(self, rows) -> None:
            super().__init__()
            self._rows = rows
            self.update_log = []

        def exclude(self, **kwargs) -> _LegacyQuerySet:
            return _LegacyQuerySet(self._rows).exclude(**kwargs)

        def filter(self, **kwargs) -> _UpdateQuerySet:
            assert "pk" in kwargs
            return _UpdateQuerySet(self.update_log, kwargs["pk"])

    class ContentTypeManager(_AliasManager):
        def get_or_create(self, **kwargs) -> tuple[SimpleNamespace, bool]:
            assert kwargs == {"app_label": source_app_label, "model": source_model_name}
            return ct, False

        def filter(self, **kwargs) -> Any:
            assert kwargs == {"app_label": source_app_label, "model": source_model_name}
            row = ct

            class _Filtered:
                def first(_self) -> SimpleNamespace:
                    return row

            return _Filtered()

    class DocumentIdManager(_AliasManager):
        def __init__(self) -> None:
            super().__init__()
            self.created = []

        def get_or_create(self, **kwargs) -> tuple[SimpleNamespace, bool]:
            doc = _DocumentRowFactory(
                id=1000 + kwargs["object_id"],
                content_type_id=kwargs["content_type_id"],
                object_id=kwargs["object_id"],
            )
            self.created.append(kwargs)
            return doc, True

    class MetadataManager(_AliasManager):
        def __init__(self) -> None:
            super().__init__()
            self.updates = []
            self.metadata_rows = []

        def update_or_create(self, **kwargs) -> tuple[SimpleNamespace, bool]:
            self.updates.append(kwargs)
            return SimpleNamespace(), True

        def filter(self, **kwargs) -> Any:
            class _MetadataQuerySet:
                def __init__(self, rows) -> None:
                    self._rows = rows

                def select_related(self, *_args) -> "_MetadataQuerySet":
                    return self

                def __iter__(self) -> Iterator[SimpleNamespace]:
                    return iter(self._rows)

            return _MetadataQuerySet([])

    source_manager = SourceManager(source_rows)
    ct_manager = ContentTypeManager()
    doc_manager = DocumentIdManager()
    metadata_manager = MetadataManager()

    source_model = SimpleNamespace(
        _meta=SimpleNamespace(app_label=source_app_label, model_name=source_model_name),
        objects=source_manager,
    )

    class FakeApps:
        def get_model(self, app_label, model_name) -> SimpleNamespace:
            mapping = {
                (source_app_label, source_model_name.title()): source_model,
                ("contenttypes", "ContentType"): SimpleNamespace(objects=ct_manager),
                ("baseapp_core", "DocumentId"): SimpleNamespace(objects=doc_manager),
                ("comments", "CommentableMetadata"): SimpleNamespace(objects=metadata_manager),
            }
            return mapping[(app_label, model_name)]

    return FakeApps(), source_manager, ct_manager, doc_manager, metadata_manager


def test_migrate_uses_db_alias_from_schema_editor() -> None:
    source_rows = [_ModelRowFactory(pk=1)]
    ct = _ContentTypeRowFactory()
    apps, source_m, ct_m, doc_m, meta_m = _alias_tracking_apps(source_rows=source_rows, ct=ct)
    se = SimpleNamespace(connection=SimpleNamespace(alias="replica"))

    migrate_legacy_commentable_fields_to_metadata(
        apps,
        schema_editor=se,
        source_app_label="pages",
        source_model_name="Page",
    )

    assert source_m.using_log == ["replica"]
    assert ct_m.using_log == ["replica"]
    assert doc_m.using_log == ["replica"]
    assert meta_m.using_log == ["replica"]


def test_reverse_migrate_uses_db_alias_from_schema_editor() -> None:
    apps, source_m, ct_m, _, meta_m = _alias_tracking_apps(
        source_rows=[], ct=_ContentTypeRowFactory()
    )
    se = SimpleNamespace(connection=SimpleNamespace(alias="replica"))

    reverse_migrate_legacy_commentable_fields_from_metadata(
        apps,
        schema_editor=se,
        source_app_label="pages",
        source_model_name="Page",
    )

    # The reverse path does NOT touch DocumentId, so we only assert the three managers
    # it actually uses got pinned to the alias.
    assert source_m.using_log == ["replica"]
    assert ct_m.using_log == ["replica"]
    assert meta_m.using_log == ["replica"]
