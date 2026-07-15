from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any, NoReturn

import factory

from baseapp_reactions.migration_helpers.convert_legacy_reactable_fields_to_metadata_helper import (
    migrate_legacy_reactable_fields_to_metadata,
    reverse_migrate_legacy_reactable_fields_from_metadata,
)


class _ModelRowFactory(factory.Factory):
    class Meta:
        model = SimpleNamespace

    pk = factory.Sequence(lambda n: n + 1)
    reactions_count = factory.LazyFunction(lambda: {"total": 0, "LIKE": 0, "DISLIKE": 0})
    is_reactions_enabled = True


class _ContentTypeRowFactory(factory.Factory):
    class Meta:
        model = SimpleNamespace

    id = 77
    app_label = "comments"
    model = "comment"


class _DocumentRowFactory(factory.Factory):
    class Meta:
        model = SimpleNamespace

    id = 1001
    content_type_id = 77
    object_id = 1


class _LegacyQuerySet:
    """Minimal queryset shim — the helper calls `only()`, iteration."""

    def __init__(self, rows) -> None:
        self._rows = list(rows)

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

    def only(self, *_args) -> _LegacyQuerySet:
        return _LegacyQuerySet(self._rows)

    def filter(self, **kwargs) -> _UpdateQuerySet:
        if "pk" in kwargs:
            return _UpdateQuerySet(self.update_log, kwargs["pk"])
        raise AssertionError("Unexpected filter call")


def _make_apps(*, source_model, content_type, get_or_create_log, metadata_log) -> Any:
    class ContentTypeManager:
        def get_or_create(self, **kwargs) -> tuple[SimpleNamespace, bool]:
            assert kwargs == {
                "app_label": source_model._meta.app_label,
                "model": source_model._meta.model_name,
            }
            return content_type, False

        def filter(self, **kwargs) -> Any:
            assert kwargs == {
                "app_label": source_model._meta.app_label,
                "model": source_model._meta.model_name,
            }

            class _Filtered:
                def first(_self) -> SimpleNamespace:
                    return content_type

            return _Filtered()

    class DocumentIdManager:
        def get_or_create(self, **kwargs) -> tuple[SimpleNamespace, bool]:
            doc = _DocumentRowFactory(
                id=1000 + kwargs["object_id"],
                content_type_id=kwargs["content_type_id"],
                object_id=kwargs["object_id"],
            )
            get_or_create_log.append(kwargs)
            return doc, True

    class ReactableMetadataManager:
        def update_or_create(self, **kwargs) -> tuple[SimpleNamespace, bool]:
            metadata_log.append(kwargs)
            return SimpleNamespace(), True

    class FakeApps:
        def get_model(self, app_label, model_name) -> SimpleNamespace:
            mapping = {
                ("comments", "Comment"): source_model,
                ("contenttypes", "ContentType"): SimpleNamespace(objects=ContentTypeManager()),
                ("baseapp_core", "DocumentId"): SimpleNamespace(objects=DocumentIdManager()),
                ("baseapp_reactions", "ReactableMetadata"): SimpleNamespace(
                    objects=ReactableMetadataManager()
                ),
            }
            return mapping[(app_label, model_name)]

    return FakeApps()


def test_migrate_legacy_reactable_fields_to_metadata_creates_metadata_rows() -> None:
    source_rows = [
        _ModelRowFactory(
            pk=1,
            reactions_count={"total": 3, "LIKE": 2, "DISLIKE": 1},
            is_reactions_enabled=False,
        ),
        _ModelRowFactory(
            pk=2,
            reactions_count={"total": 1, "LIKE": 1, "DISLIKE": 0},
            is_reactions_enabled=True,
        ),
    ]
    source_model = SimpleNamespace(
        _meta=SimpleNamespace(app_label="comments", model_name="comment"),
        objects=_SourceManager(source_rows),
    )
    ct = _ContentTypeRowFactory(id=77, app_label="comments", model="comment")
    created_docs = []
    metadata_updates = []

    apps = _make_apps(
        source_model=source_model,
        content_type=ct,
        get_or_create_log=created_docs,
        metadata_log=metadata_updates,
    )

    migrate_legacy_reactable_fields_to_metadata(
        apps,
        schema_editor=None,
        source_app_label="comments",
        source_model_name="Comment",
    )

    assert created_docs == [
        {"content_type_id": 77, "object_id": 1},
        {"content_type_id": 77, "object_id": 2},
    ]
    assert metadata_updates == [
        {
            "target_id": 1001,
            "defaults": {
                "reactions_count": {"total": 3, "LIKE": 2, "DISLIKE": 1},
                "is_reactions_enabled": False,
            },
        },
        {
            "target_id": 1002,
            "defaults": {
                "reactions_count": {"total": 1, "LIKE": 1, "DISLIKE": 0},
                "is_reactions_enabled": True,
            },
        },
    ]


def test_migrate_legacy_reactable_fields_no_op_when_no_source_rows() -> None:
    """Empty source table → helper creates no DocumentId or metadata rows.
    ContentType is upserted via ``get_or_create`` so the helper is safe on a
    fresh test DB where ``post_migrate`` hasn't yet populated the row."""
    source_model = SimpleNamespace(
        _meta=SimpleNamespace(app_label="comments", model_name="comment"),
        objects=_SourceManager([]),
    )
    ct = _ContentTypeRowFactory(id=77, app_label="comments", model="comment")
    created_docs = []
    metadata_updates = []

    apps = _make_apps(
        source_model=source_model,
        content_type=ct,
        get_or_create_log=created_docs,
        metadata_log=metadata_updates,
    )

    migrate_legacy_reactable_fields_to_metadata(
        apps,
        schema_editor=None,
        source_app_label="comments",
        source_model_name="Comment",
    )

    assert created_docs == []
    assert metadata_updates == []


def test_reverse_migrate_legacy_reactable_fields_restores_source_fields() -> None:
    source_model = SimpleNamespace(
        _meta=SimpleNamespace(app_label="comments", model_name="comment"),
        objects=_SourceManager([]),
    )
    ct = _ContentTypeRowFactory(id=77, app_label="comments", model="comment")
    metadata_rows = [
        SimpleNamespace(
            reactions_count={"total": 5, "LIKE": 5, "DISLIKE": 0},
            is_reactions_enabled=False,
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
            assert kwargs == {"app_label": "comments", "model": "comment"}

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
                ("comments", "Comment"): source_model,
                ("contenttypes", "ContentType"): SimpleNamespace(objects=ContentTypeManager()),
                ("baseapp_reactions", "ReactableMetadata"): SimpleNamespace(
                    objects=MetadataManager()
                ),
            }
            return mapping[(app_label, model_name)]

    reverse_migrate_legacy_reactable_fields_from_metadata(
        FakeApps(),
        schema_editor=None,
        source_app_label="comments",
        source_model_name="Comment",
    )

    assert source_model.objects.update_log == [
        (
            10,
            {
                "reactions_count": {"total": 5, "LIKE": 5, "DISLIKE": 0},
                "is_reactions_enabled": False,
            },
        )
    ]


def test_reverse_migrate_legacy_reactable_fields_no_op_when_content_type_missing() -> None:
    source_model = SimpleNamespace(
        _meta=SimpleNamespace(app_label="comments", model_name="comment"),
        objects=_SourceManager([]),
    )

    class ContentTypeManager:
        def filter(self, **_kwargs) -> Any:
            class _Filtered:
                def first(_self) -> None:
                    return None

            return _Filtered()

    class MetadataManager:
        def filter(self, **kwargs) -> NoReturn:
            raise AssertionError("Should not query metadata when ContentType is missing")

    class FakeApps:
        def get_model(self, app_label, model_name) -> SimpleNamespace:
            mapping = {
                ("comments", "Comment"): source_model,
                ("contenttypes", "ContentType"): SimpleNamespace(objects=ContentTypeManager()),
                ("baseapp_reactions", "ReactableMetadata"): SimpleNamespace(
                    objects=MetadataManager()
                ),
            }
            return mapping[(app_label, model_name)]

    reverse_migrate_legacy_reactable_fields_from_metadata(
        FakeApps(),
        schema_editor=None,
        source_app_label="comments",
        source_model_name="Comment",
    )

    assert source_model.objects.update_log == []
