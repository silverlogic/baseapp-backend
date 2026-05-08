from types import SimpleNamespace
from unittest.mock import patch

import factory
import pytest

from baseapp_reactions.migration_helpers.seed_reactable_metadata_from_reactions_helper import (
    reverse_seed_reactable_metadata,
    seed_reactable_metadata_from_reactions,
)


class _ReactionTypes:
    """Shim mimicking `Reaction.ReactionTypes` (an `IntegerChoices` enum)."""

    LIKE = SimpleNamespace(value=1, name="LIKE")
    DISLIKE = SimpleNamespace(value=-1, name="DISLIKE")

    def __iter__(self):
        return iter([self.LIKE, self.DISLIKE])


REACTION_TYPES = _ReactionTypes()


class _FakeFlatList(list):
    def distinct(self):
        seen = []
        for row in self:
            if row not in seen:
                seen.append(row)
        return seen


class _GroupedQuerySet:
    """Mimics ``.values(*keys).annotate(n=Count("id"))`` — yields one row per
    distinct (target_document_id, reaction_type) tuple with an `n` count."""

    def __init__(self, rows):
        self._rows = list(rows)

    def annotate(self, **kwargs):
        # The helper calls `.annotate(n=Count("id"))`; group rows by their
        # current dict shape and emit `{**group_key, "n": count}`.
        groups: dict[tuple, int] = {}
        order: list[tuple] = []
        for row in self._rows:
            key = tuple(sorted(row.items()))
            if key not in groups:
                order.append(key)
            groups[key] = groups.get(key, 0) + 1
        return [{**dict(k), "n": groups[k]} for k in order]


class _FakeQuerySet:
    def __init__(self, rows):
        self._rows = list(rows)

    def exclude(self, **kwargs):
        return self._apply(**kwargs, exclude=True)

    def filter(self, **kwargs):
        return self._apply(**kwargs, exclude=False)

    def _apply(self, exclude=False, **kwargs):
        rows = self._rows
        for key, value in kwargs.items():
            if key.endswith("__isnull"):
                field = key.replace("__isnull", "")

                def _is_null(row, _f=field):
                    if hasattr(row, _f):
                        return getattr(row, _f) is None
                    return getattr(row, f"{_f}_id", None) is None

                if exclude:
                    rows = [r for r in rows if _is_null(r) != value]
                else:
                    rows = [r for r in rows if _is_null(r) == value]
            elif key.endswith("__in"):
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

    def values(self, *fields):
        return _GroupedQuerySet([{f: getattr(r, f) for f in fields} for r in self._rows])

    def count(self):
        return len(self._rows)


class _FakeManager:
    def __init__(self, rows=None):
        self._rows = list(rows or [])
        self.update_log = []
        self.delete_log = []

    def filter(self, **kwargs):
        manager = self
        matched = _FakeQuerySet(manager._rows).filter(**kwargs)._rows

        class _MatchedQS(_FakeQuerySet):
            def delete(self):
                manager.delete_log.append(kwargs)
                manager._rows = [r for r in manager._rows if r not in matched]

        return _MatchedQS(matched)

    def exclude(self, **kwargs):
        return _FakeQuerySet(self._rows).exclude(**kwargs)

    def update_or_create(self, defaults=None, **kwargs):
        defaults = defaults or {}
        self.update_log.append({**kwargs, "defaults": defaults})
        return SimpleNamespace(**kwargs, **defaults), True


class _ReactionFactory(factory.Factory):
    class Meta:
        model = SimpleNamespace

    pk = factory.Sequence(lambda n: n + 1)
    target_document_id = 1000
    reaction_type = 1  # LIKE


def _make_apps(*, reactions, metadata_rows=None):
    reaction_manager = _FakeManager(reactions)
    metadata_manager = _FakeManager(metadata_rows or [])

    reaction_model = SimpleNamespace(objects=reaction_manager, ReactionTypes=REACTION_TYPES)
    metadata_model = SimpleNamespace(objects=metadata_manager)

    class FakeApps:
        def get_model(self, app_label, model_name):
            mapping = {
                ("baseapp_reactions", "Reaction"): reaction_model,
                ("baseapp_reactions", "ReactableMetadata"): metadata_model,
                # Swap-target labels (BASEAPP_REACTIONS_*_MODEL points at "reactions.*")
                ("reactions", "Reaction"): reaction_model,
                ("reactions", "ReactableMetadata"): metadata_model,
            }
            return mapping[(app_label, model_name)]

    return FakeApps(), reaction_manager, metadata_manager


@pytest.fixture(autouse=True)
def _stub_swapper_is_not_swapped():
    """Force the helper through `apps.get_model` instead of `swapper.load_model`."""
    with patch(
        "baseapp_reactions.migration_helpers.seed_reactable_metadata_from_reactions_helper.get_apps_model",
        side_effect=lambda apps, app_label, model_name: apps.get_model(app_label, model_name),
    ):
        yield


def test_seed_reactable_metadata_creates_one_row_per_unique_target():
    reactions = [
        _ReactionFactory(pk=1, target_document_id=10, reaction_type=1),  # LIKE
        _ReactionFactory(pk=2, target_document_id=10, reaction_type=1),  # LIKE
        _ReactionFactory(pk=3, target_document_id=10, reaction_type=-1),  # DISLIKE
        _ReactionFactory(pk=4, target_document_id=20, reaction_type=1),  # LIKE
    ]
    apps, _, metadata_manager = _make_apps(reactions=reactions)

    seed_reactable_metadata_from_reactions(apps, schema_editor=None)

    # One metadata write per distinct target_document, in iteration order.
    assert len(metadata_manager.update_log) == 2
    first, second = metadata_manager.update_log
    # target=10 → 2 LIKE + 1 DISLIKE = 3 total
    assert first["target_id"] == 10
    assert first["defaults"]["reactions_count"] == {"total": 3, "LIKE": 2, "DISLIKE": 1}
    # target=20 → 1 LIKE
    assert second["target_id"] == 20
    assert second["defaults"]["reactions_count"] == {"total": 1, "LIKE": 1, "DISLIKE": 0}


def test_seed_reactable_metadata_no_op_when_no_reactions():
    apps, _, metadata_manager = _make_apps(reactions=[])

    seed_reactable_metadata_from_reactions(apps, schema_editor=None)

    assert metadata_manager.update_log == []


def test_seed_reactable_metadata_skips_reactions_with_null_target():
    reactions = [
        _ReactionFactory(pk=1, target_document_id=None, reaction_type=1),
        _ReactionFactory(pk=2, target_document_id=20, reaction_type=-1),
    ]
    apps, _, metadata_manager = _make_apps(reactions=reactions)

    seed_reactable_metadata_from_reactions(apps, schema_editor=None)

    assert len(metadata_manager.update_log) == 1
    assert metadata_manager.update_log[0]["target_id"] == 20
    assert metadata_manager.update_log[0]["defaults"]["reactions_count"] == {
        "total": 1,
        "LIKE": 0,
        "DISLIKE": 1,
    }


def test_reverse_seed_reactable_metadata_deletes_metadata_for_known_doc_ids():
    reactions = [_ReactionFactory(pk=1, target_document_id=100, reaction_type=1)]
    apps, _, metadata_manager = _make_apps(
        reactions=reactions,
        metadata_rows=[
            SimpleNamespace(target_id=100),
            SimpleNamespace(target_id=999),  # unrelated metadata
        ],
    )

    reverse_seed_reactable_metadata(apps, schema_editor=None)

    assert len(metadata_manager.delete_log) == 1
    assert metadata_manager.delete_log[0] == {"target_id__in": [100]}


def test_reverse_seed_reactable_metadata_no_op_when_no_reactions():
    apps, _, metadata_manager = _make_apps(reactions=[])

    reverse_seed_reactable_metadata(apps, schema_editor=None)

    assert metadata_manager.delete_log == []
