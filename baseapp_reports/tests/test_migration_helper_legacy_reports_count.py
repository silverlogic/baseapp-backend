from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any, NoReturn

import factory

from baseapp_reports.migration_helpers.convert_legacy_reports_count_to_metadata_helper import (
    migrate_legacy_reports_count_to_metadata,
    reverse_migrate_legacy_reports_count_from_metadata,
)


class _ModelRowFactory(factory.Factory):
    class Meta:
        model = SimpleNamespace

    pk = factory.Sequence(lambda n: n + 1)
    reports_count = factory.LazyFunction(lambda: {"total": 0})


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
    """Minimal queryset shim — the helper only calls `exists()`, `exclude()`,
    `only()`, and iteration."""

    def __init__(self, rows) -> None:
        self._rows = list(rows)

    def exists(self) -> bool:
        return bool(self._rows)

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


def _make_apps(*, source_model, content_type, get_or_create_log, metadata_log) -> Any:
    class ContentTypeManager:
        def get_or_create(self, **kwargs) -> tuple[SimpleNamespace, bool]:
            assert kwargs == {"app_label": "profiles", "model": "profile"}
            return content_type, False

        def filter(self, **kwargs) -> Any:
            assert kwargs == {"app_label": "profiles", "model": "profile"}

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

    class ReportableMetadataManager:
        def update_or_create(self, **kwargs) -> tuple[SimpleNamespace, bool]:
            metadata_log.append(kwargs)
            return SimpleNamespace(), True

        def filter(self, **kwargs) -> "_MetadataQuerySet":
            assert kwargs == {"target__content_type_id": content_type.id}
            return _MetadataQuerySet(metadata_log.get("rows", []))

    class FakeApps:
        def get_model(self, app_label, model_name) -> SimpleNamespace:
            mapping = {
                ("profiles", "Profile"): source_model,
                ("contenttypes", "ContentType"): SimpleNamespace(objects=ContentTypeManager()),
                ("baseapp_core", "DocumentId"): SimpleNamespace(objects=DocumentIdManager()),
                ("baseapp_reports", "ReportableMetadata"): SimpleNamespace(
                    objects=ReportableMetadataManager()
                ),
            }
            return mapping[(app_label, model_name)]

    return FakeApps()


class _MetadataQuerySet:
    def __init__(self, rows) -> None:
        self._rows = rows

    def select_related(self, *_args) -> "_MetadataQuerySet":
        return self

    def __iter__(self) -> Iterator[SimpleNamespace]:
        return iter(self._rows)


def test_migrate_legacy_reports_count_to_metadata_creates_metadata_rows() -> None:
    source_rows = [
        _ModelRowFactory(pk=1, reports_count={"total": 3, "spam": 2, "scam": 1}),
        _ModelRowFactory(pk=2, reports_count={"total": 1, "spam": 0, "scam": 1}),
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

    migrate_legacy_reports_count_to_metadata(
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
        {
            "target_id": 1001,
            "defaults": {"reports_count": {"total": 3, "spam": 2, "scam": 1}},
        },
        {
            "target_id": 1002,
            "defaults": {"reports_count": {"total": 1, "spam": 0, "scam": 1}},
        },
    ]


def test_migrate_legacy_reports_count_no_op_when_no_source_rows() -> None:
    """Empty source table → helper creates no DocumentId or metadata rows. ContentType
    is upserted via `get_or_create` so the helper is safe on a fresh test DB where
    `post_migrate` hasn't yet populated the row."""
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

    migrate_legacy_reports_count_to_metadata(
        apps,
        schema_editor=None,
        source_app_label="profiles",
        source_model_name="Profile",
    )

    assert created_docs == []
    assert metadata_updates == []


def test_reverse_migrate_legacy_reports_count_restores_source_field() -> None:
    source_model = SimpleNamespace(
        _meta=SimpleNamespace(app_label="profiles", model_name="profile"),
        objects=_SourceManager([]),
    )
    ct = _ContentTypeRowFactory(id=77, app_label="profiles", model="profile")
    metadata_rows = [
        SimpleNamespace(
            reports_count={"total": 5, "spam": 5},
            target=SimpleNamespace(object_id=10),
        )
    ]

    class _MetadataQS:
        def __init__(self, rows) -> None:
            self._rows = rows

        def select_related(self, *_args) -> "_MetadataQS":
            return self

        def __iter__(self) -> Iterator[SimpleNamespace]:
            return iter(self._rows)

    class ContentTypeManager:
        def filter(self, **kwargs) -> Any:
            assert kwargs == {"app_label": "profiles", "model": "profile"}

            class _Filtered:
                def first(_self) -> SimpleNamespace:
                    return ct

            return _Filtered()

    class MetadataManager:
        def filter(self, **kwargs) -> "_MetadataQS":
            assert kwargs == {"target__content_type_id": 77}
            return _MetadataQS(metadata_rows)

    class FakeApps:
        def get_model(self, app_label, model_name) -> SimpleNamespace:
            mapping = {
                ("profiles", "Profile"): source_model,
                ("contenttypes", "ContentType"): SimpleNamespace(objects=ContentTypeManager()),
                ("baseapp_reports", "ReportableMetadata"): SimpleNamespace(
                    objects=MetadataManager()
                ),
            }
            return mapping[(app_label, model_name)]

    reverse_migrate_legacy_reports_count_from_metadata(
        FakeApps(),
        schema_editor=None,
        source_app_label="profiles",
        source_model_name="Profile",
    )

    assert source_model.objects.update_log == [(10, {"reports_count": {"total": 5, "spam": 5}})]


def test_reverse_migrate_legacy_reports_count_no_op_when_content_type_missing() -> None:
    """Reverse on a fresh DB where the source app's ContentType row does not exist yet
    must not raise — it's the symmetric edge case to `test_migrate_..._no_op`."""
    source_model = SimpleNamespace(
        _meta=SimpleNamespace(app_label="profiles", model_name="profile"),
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
                ("profiles", "Profile"): source_model,
                ("contenttypes", "ContentType"): SimpleNamespace(objects=ContentTypeManager()),
                ("baseapp_reports", "ReportableMetadata"): SimpleNamespace(
                    objects=MetadataManager()
                ),
            }
            return mapping[(app_label, model_name)]

    reverse_migrate_legacy_reports_count_from_metadata(
        FakeApps(),
        schema_editor=None,
        source_app_label="profiles",
        source_model_name="Profile",
    )

    assert source_model.objects.update_log == []
