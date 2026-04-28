from types import SimpleNamespace

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
    def __init__(self, rows):
        self._rows = list(rows)

    def exclude(self, **kwargs):
        rows = self._rows
        for key, value in kwargs.items():
            if key.endswith("__isnull"):
                field = key.replace("__isnull", "")
                rows = [r for r in rows if (getattr(r, field) is None) != value]
            else:
                rows = [r for r in rows if getattr(r, key) != value]
        return _LegacyQuerySet(rows)

    def only(self, *_args):
        return self

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

    def exclude(self, **kwargs):
        return _LegacyQuerySet(self._rows).exclude(**kwargs)

    def filter(self, **kwargs):
        if "pk" in kwargs:
            return _UpdateQuerySet(self.update_log, kwargs["pk"])
        raise AssertionError("Unexpected filter call")


def test_migrate_legacy_commentable_fields_to_metadata_creates_metadata_rows():
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
        def get(self, **kwargs):
            assert kwargs == {"app_label": "pages", "model": "page"}
            return ct

    class DocumentIdManager:
        def get_or_create(self, **kwargs):
            doc = _DocumentRowFactory(
                id=1000 + kwargs["object_id"],
                content_type_id=kwargs["content_type_id"],
                object_id=kwargs["object_id"],
            )
            created_docs.append(kwargs)
            return doc, True

    class CommentableMetadataManager:
        def update_or_create(self, **kwargs):
            metadata_updates.append(kwargs)
            return SimpleNamespace(), True

    class FakeApps:
        def get_model(self, app_label, model_name):
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


def test_reverse_migrate_legacy_commentable_fields_from_metadata_restores_source_fields():
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
        def __init__(self, rows):
            self._rows = rows

        def select_related(self, *_args):
            return self

        def __iter__(self):
            return iter(self._rows)

    class ContentTypeManager:
        def get(self, **kwargs):
            assert kwargs == {"app_label": "pages", "model": "page"}
            return ct

    class MetadataManager:
        def filter(self, **kwargs):
            assert kwargs == {"target__content_type_id": 77}
            return _MetadataQuerySet(metadata_rows)

    class FakeApps:
        def get_model(self, app_label, model_name):
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
