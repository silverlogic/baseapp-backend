from types import SimpleNamespace

import factory
import pytest

from baseapp_comments.migration_helpers import (
    convert_comments_gfk_into_document_id_helper as gfk,
)
from baseapp_comments.migration_helpers.convert_comments_gfk_into_document_id_helper import (
    assert_all_comment_rows_have_target_document,
    assert_all_commentevent_rows_have_target_document,
    migrate_comment_targets_to_document_id,
    reverse_migrate_comment_targets_to_generic_fk,
)


class _FakeQuerySet:
    def __init__(self, rows):
        self._rows = list(rows)

    def using(self, _alias):
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

    def values_list(self, *fields):
        return _FakeValueList([tuple(getattr(r, f) for f in fields) for r in self._rows])

    def select_related(self, *_args):
        return self

    def __iter__(self):
        return iter(self._rows)

    def first(self):
        return self._rows[0] if self._rows else None

    def iterator(self):
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
    def __init__(self, manager, pk, update_log):
        self._manager = manager
        self._pk = pk
        self._update_log = update_log

    def first(self):
        for row in self._manager._rows:
            if getattr(row, "pk", None) == self._pk:
                return row
        return None

    def update(self, **kwargs):
        self._update_log.append((self._pk, kwargs))
        for row in self._manager._rows:
            if getattr(row, "pk", None) == self._pk:
                for k, v in kwargs.items():
                    setattr(row, k, v)
                break


class _FakeManager:
    def __init__(self, rows):
        self._rows = list(rows)
        self.update_log = []

    def using(self, _alias):
        return self

    def exclude(self, **kwargs):
        return _FakeQuerySet(self._rows).exclude(**kwargs)

    def filter(self, **kwargs):
        if "pk" in kwargs:
            return _FakeUpdateQuerySet(self, kwargs["pk"], self.update_log)
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
    pgh_obj_id = None


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


def test_migrate_copies_target_document_onto_event_from_pghistory_comment():
    """
    GFK backfill skips events with NULL target_content_type; pghistory backfill
    should still set target_document from the snapshot comment (pgh_obj).
    """
    comments = [
        _CommentLegacyFactory(pk=1, target_content_type_id=10, target_object_id=100),
    ]
    events = [
        _CommentEventLegacyFactory(
            pk=20,
            target_content_type_id=None,
            target_object_id=None,
            target_document_id=None,
            pgh_obj_id=1,
        ),
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
    # Comment row updated to 900 in GFK loop; pgh backfill should copy it onto the event
    assert apps.event_model.objects.update_log == [
        (20, {"target_document_id": 900}),
    ]


def test_assert_all_comment_rows_have_target_document_passes_for_filled_column():
    comments = [
        _CommentLegacyFactory(
            pk=1, target_content_type_id=10, target_object_id=100, target_document_id=1
        )
    ]
    comment_model = SimpleNamespace(objects=_FakeManager(comments))

    class FakeApps:
        def get_model(self, app_label, model_name):
            if (app_label, model_name) == ("comments", "Comment"):
                return comment_model
            raise AssertionError("Unexpected model lookup")

    assert_all_comment_rows_have_target_document(FakeApps(), schema_editor=None)


def test_assert_all_comment_rows_have_target_document_uses_db_alias_from_schema_editor():
    comments = [
        _CommentLegacyFactory(
            pk=1, target_content_type_id=10, target_object_id=100, target_document_id=1
        )
    ]
    comment_model = SimpleNamespace(objects=_FakeManager(comments))
    se = SimpleNamespace(connection=SimpleNamespace(alias="replica"))

    class FakeApps:
        def get_model(self, app_label, model_name):
            if (app_label, model_name) == ("comments", "Comment"):
                return comment_model
            raise AssertionError("Unexpected model lookup")

    assert_all_comment_rows_have_target_document(FakeApps(), schema_editor=se)


def test_assert_all_comment_rows_have_target_document_raises_when_still_empty():
    comments = [
        _CommentLegacyFactory(
            pk=1,
            target_content_type_id=None,
            target_object_id=None,
            target_document_id=None,
        )
    ]
    comment_model = SimpleNamespace(objects=_FakeManager(comments))

    class FakeApps:
        def get_model(self, app_label, model_name):
            if (app_label, model_name) == ("comments", "Comment"):
                return comment_model
            raise AssertionError("Unexpected model lookup")

    with pytest.raises(ValueError, match="1 row\\(s\\) still have target_document_id NULL"):
        assert_all_comment_rows_have_target_document(FakeApps(), schema_editor=None)


def test_assert_all_commentevent_rows_have_target_document_passes_for_filled_column():
    events = [
        _CommentEventLegacyFactory(
            pk=1, target_content_type_id=10, target_object_id=100, target_document_id=1
        )
    ]
    event_model = SimpleNamespace(objects=_FakeManager(events))

    class FakeApps:
        def get_model(self, app_label, model_name):
            if (app_label, model_name) == ("comments", "CommentEvent"):
                return event_model
            raise AssertionError("Unexpected model lookup")

    assert_all_commentevent_rows_have_target_document(FakeApps(), schema_editor=None)


def test_assert_all_commentevent_rows_have_target_document_raises_when_still_empty():
    events = [
        _CommentEventLegacyFactory(
            pk=1,
            target_content_type_id=None,
            target_object_id=None,
            target_document_id=None,
        )
    ]
    event_model = SimpleNamespace(objects=_FakeManager(events))

    class FakeApps:
        def get_model(self, app_label, model_name):
            if (app_label, model_name) == ("comments", "CommentEvent"):
                return event_model
            raise AssertionError("Unexpected model lookup")

    with pytest.raises(ValueError, match="1 commentevent row\\(s\\) still have target_document_id"):
        assert_all_commentevent_rows_have_target_document(FakeApps(), schema_editor=None)


def test_migrate_comment_targets_raises_at_assert_when_gfk_both_null():
    """Orphan comments (no GFK) keep NULL target_document; end-of-migrate assert must fail."""
    comments = [
        _CommentLegacyFactory(
            pk=1,
            target_content_type_id=None,
            target_object_id=None,
            target_document_id=None,
        )
    ]
    events = []

    class FakeDocumentIdManager:
        def values(self, *_args):
            return []

        def create(self, content_type_id, object_id):
            return SimpleNamespace(id=1, content_type_id=content_type_id, object_id=object_id)

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

    with pytest.raises(ValueError, match="1 row\\(s\\) still have target_document_id NULL"):
        migrate_comment_targets_to_document_id(FakeApps(), schema_editor=None)


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


def test_migrate_ends_by_calling_post_backfill_assert(monkeypatch):
    calls = []

    def capture(apps, schema_editor=None):
        calls.append((apps, schema_editor))

    monkeypatch.setattr(gfk, "assert_all_comment_rows_have_target_document", capture)
    monkeypatch.setattr(gfk, "assert_all_commentevent_rows_have_target_document", capture)
    comments = [
        _CommentLegacyFactory(pk=1, target_content_type_id=10, target_object_id=100),
    ]
    events = []
    m = _FakeManager(comments)
    m_event = _FakeManager(events)

    class FakeDocumentIdManager:
        def values(self, *_args):
            return [_DocumentIdRowFactory(id=900, content_type_id=10, object_id=100)]

        def create(self, *args, **kwargs):
            raise AssertionError("should not need new doc")

    class FakeApps:
        def __init__(self):
            self.document_manager = FakeDocumentIdManager()
            self.comment_model = SimpleNamespace(objects=m)
            self.event_model = SimpleNamespace(objects=m_event)

        def get_model(self, app_label, model_name):
            if (app_label, model_name) == ("comments", "Comment"):
                return self.comment_model
            if (app_label, model_name) == ("comments", "CommentEvent"):
                return self.event_model
            if (app_label, model_name) == ("baseapp_core", "DocumentId"):
                return SimpleNamespace(objects=self.document_manager)
            raise AssertionError("Unexpected model lookup")

    se = object()
    migrate_comment_targets_to_document_id(FakeApps(), schema_editor=se)
    assert len(calls) == 2
    assert calls[0][1] is se
    assert calls[1][1] is se
