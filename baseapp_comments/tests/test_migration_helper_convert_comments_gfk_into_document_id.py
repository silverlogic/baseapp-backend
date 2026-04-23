from types import SimpleNamespace

import factory

from baseapp_comments.migration_helpers.convert_comments_gfk_into_document_id_helper import (
    migrate_comment_targets_to_document_id,
    reverse_migrate_comment_targets_to_generic_fk,
)


class _FakeQuerySet:
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
        return _FakeQuerySet(rows)

    def filter(self, **kwargs):
        rows = self._rows
        for key, value in kwargs.items():
            if key.endswith("__isnull"):
                field = key.replace("__isnull", "")
                rows = [r for r in rows if (getattr(r, field) is None) == value]
            else:
                rows = [r for r in rows if getattr(r, key) == value]
        return _FakeQuerySet(rows)

    def values_list(self, *fields):
        return _FakeValueList([tuple(getattr(r, f) for f in fields) for r in self._rows])

    def select_related(self, *_args):
        return self

    def __iter__(self):
        return iter(self._rows)


class _FakeValueList:
    def __init__(self, rows):
        self._rows = rows

    def distinct(self):
        seen = []
        for row in self._rows:
            if row not in seen:
                seen.append(row)
        return seen


class _FakeUpdateQuerySet:
    def __init__(self, update_log, pk):
        self._update_log = update_log
        self._pk = pk

    def update(self, **kwargs):
        self._update_log.append((self._pk, kwargs))


class _FakeManager:
    def __init__(self, rows):
        self._rows = rows
        self.update_log = []

    def exclude(self, **kwargs):
        return _FakeQuerySet(self._rows).exclude(**kwargs)

    def filter(self, **kwargs):
        if "pk" in kwargs:
            return _FakeUpdateQuerySet(self.update_log, kwargs["pk"])
        return _FakeQuerySet(self._rows).filter(**kwargs)


class _CommentLegacyFactory(factory.Factory):
    class Meta:
        model = SimpleNamespace

    pk = factory.Sequence(lambda n: n + 1)
    target_content_type_id = 10
    target_object_id = factory.Sequence(lambda n: n + 100)
    target_document_id = None


class _CommentEventLegacyFactory(factory.Factory):
    class Meta:
        model = SimpleNamespace

    pk = factory.Sequence(lambda n: n + 20)
    target_content_type_id = 10
    target_object_id = factory.Sequence(lambda n: n + 100)
    target_document_id = None


class _DocumentIdRowFactory(factory.Factory):
    class Meta:
        model = dict

    id = 900
    content_type_id = 10
    object_id = 100


def test_migrate_comment_targets_to_document_id_maps_rows_and_creates_missing_doc():
    comments = [
        _CommentLegacyFactory(pk=1, target_content_type_id=10, target_object_id=100),
        _CommentLegacyFactory(pk=2, target_content_type_id=11, target_object_id=200),
    ]
    events = [
        _CommentEventLegacyFactory(pk=20, target_content_type_id=10, target_object_id=100),
        _CommentEventLegacyFactory(pk=21, target_content_type_id=11, target_object_id=200),
    ]

    class FakeDocumentIdManager:
        def __init__(self):
            self.created = []

        def values(self, *_args):
            return [_DocumentIdRowFactory(id=900, content_type_id=10, object_id=100)]

        def create(self, content_type_id, object_id):
            doc = SimpleNamespace(id=901, content_type_id=content_type_id, object_id=object_id)
            self.created.append(doc)
            return doc

    class FakeApps:
        def __init__(self):
            self.document_manager = FakeDocumentIdManager()
            self.comment_model = SimpleNamespace(objects=_FakeManager(comments))
            self.event_model = SimpleNamespace(objects=_FakeManager(events))

        def get_model(self, app_label, model_name):
            if (app_label, model_name) == ("comments", "Comment"):
                return self.comment_model
            if (app_label, model_name) == ("comments", "CommentEvent"):
                return self.event_model
            if (app_label, model_name) == ("baseapp_core", "DocumentId"):
                return SimpleNamespace(objects=self.document_manager)
            raise AssertionError("Unexpected model lookup")

    apps = FakeApps()

    migrate_comment_targets_to_document_id(apps, schema_editor=None)

    assert len(apps.document_manager.created) == 1
    assert apps.document_manager.created[0].content_type_id == 11
    assert apps.document_manager.created[0].object_id == 200
    assert apps.comment_model.objects.update_log == [
        (1, {"target_document_id": 900}),
        (2, {"target_document_id": 901}),
    ]
    assert apps.event_model.objects.update_log == [
        (20, {"target_document_id": 900}),
        (21, {"target_document_id": 901}),
    ]


def test_reverse_migrate_comment_targets_to_generic_fk_restores_legacy_columns():
    comments = [
        _CommentLegacyFactory(
            pk=1,
            target_content_type_id=None,
            target_object_id=None,
            target_document_id=900,
            target_document=SimpleNamespace(content_type_id=10, object_id=100),
        )
    ]
    events = [
        _CommentEventLegacyFactory(
            pk=20,
            target_content_type_id=None,
            target_object_id=None,
            target_document_id=901,
            target_document=SimpleNamespace(content_type_id=11, object_id=200),
        )
    ]

    comment_model = SimpleNamespace(objects=_FakeManager(comments))
    event_model = SimpleNamespace(objects=_FakeManager(events))

    class FakeApps:
        def get_model(self, app_label, model_name):
            if (app_label, model_name) == ("comments", "Comment"):
                return comment_model
            if (app_label, model_name) == ("comments", "CommentEvent"):
                return event_model
            raise AssertionError("Unexpected model lookup")

    reverse_migrate_comment_targets_to_generic_fk(FakeApps(), schema_editor=None)

    assert comment_model.objects.update_log == [
        (1, {"target_content_type_id": 10, "target_object_id": 100})
    ]
    assert event_model.objects.update_log == [
        (20, {"target_content_type_id": 11, "target_object_id": 200})
    ]
