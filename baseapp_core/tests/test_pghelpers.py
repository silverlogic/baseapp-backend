"""Unit tests for `baseapp_core.pghelpers`.

The two registries (`_pghistory_registry`, `_pgtrigger_registry`) and the
six public helpers are tested with `Mock` models so the tests never
mutate real model classes or trigger third-party side effects. Each
test isolates registry state via `patch.dict`.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pgtrigger
import pytest

from baseapp_core import pghelpers
from baseapp_core.pghelpers import (
    _pghistory_registry,
    _pgtrigger_registry,
    apply_pghistory_tracks,
    apply_pgtrigger_tracks,
    pghistory_register_default_track,
    pghistory_register_track,
    pgtrigger_register_default_track,
    pgtrigger_register_track,
)


def _make_model(*, abstract: bool = False, swapped: bool = False, triggers=None):
    """Build a model-shaped Mock with the `_meta` surface the helpers read."""
    meta = SimpleNamespace(abstract=abstract, swapped=swapped)
    if triggers is not None:
        meta.triggers = triggers
    model = MagicMock()
    model._meta = meta
    return model


# ---------------------------------------------------------------------------
# pghistory_register_track / pghistory_register_default_track
# ---------------------------------------------------------------------------


class TestPghistoryRegister:
    @pytest.fixture(autouse=True)
    def _isolate(self):
        with patch.dict(_pghistory_registry, {}, clear=True):
            yield

    def test_default_track_records_args_kwargs(self):
        model = _make_model()
        pghistory_register_default_track(model, "evt1", "evt2", exclude=["modified"])

        args, kwargs, is_override = _pghistory_registry[model]
        assert args == ("evt1", "evt2")
        assert kwargs == {"exclude": ["modified"]}
        assert is_override is False

    def test_default_track_returns_model(self):
        model = _make_model()
        assert pghistory_register_default_track(model, "evt") is model

    def test_default_track_raises_on_abstract_model(self):
        abstract = _make_model(abstract=True)
        with pytest.raises(ValueError, match="abstract models"):
            pghistory_register_default_track(abstract, "evt")
        assert abstract not in _pghistory_registry

    def test_decorator_track_marks_override_true(self):
        model = _make_model()
        decorator = pghistory_register_track("evt", exclude=["created"])
        result = decorator(model)

        assert result is model
        args, kwargs, is_override = _pghistory_registry[model]
        assert args == ("evt",)
        assert kwargs == {"exclude": ["created"]}
        assert is_override is True

    def test_decorator_track_raises_on_abstract_model(self):
        abstract = _make_model(abstract=True)
        decorator = pghistory_register_track("evt")
        with pytest.raises(ValueError, match="abstract models"):
            decorator(abstract)

    def test_decorator_overrides_existing_default(self):
        model = _make_model()
        pghistory_register_default_track(model, "default_evt")
        pghistory_register_track("override_evt", exclude=["x"])(model)

        args, kwargs, is_override = _pghistory_registry[model]
        assert args == ("override_evt",)
        assert kwargs == {"exclude": ["x"]}
        assert is_override is True

    def test_default_does_not_overwrite_existing_decorator_override(self):
        """Decorator wins even when the default is registered *after* it —
        this is the load-order safety guarantee the comment in
        `pghelpers.py` promises."""
        model = _make_model()
        pghistory_register_track("override_evt")(model)
        pghistory_register_default_track(model, "default_evt")

        args, _, is_override = _pghistory_registry[model]
        assert args == ("override_evt",)
        assert is_override is True

    def test_second_default_overwrites_first_default(self):
        """Two `pghistory_register_default_track` calls with no decorator
        in between — the second call wins (it's still a "default" entry)."""
        model = _make_model()
        pghistory_register_default_track(model, "first")
        pghistory_register_default_track(model, "second")

        args, _, is_override = _pghistory_registry[model]
        assert args == ("second",)
        assert is_override is False


# ---------------------------------------------------------------------------
# apply_pghistory_tracks
# ---------------------------------------------------------------------------


class TestApplyPghistoryTracks:
    @pytest.fixture(autouse=True)
    def _isolate(self):
        with patch.dict(_pghistory_registry, {}, clear=True):
            yield

    def test_invokes_pghistory_track_per_registered_model(self):
        model_a = _make_model()
        model_b = _make_model()
        pghistory_register_default_track(model_a, "ev_a", exclude=["x"])
        pghistory_register_default_track(model_b, "ev_b")

        with (
            patch.object(pghelpers, "pghistory") as mock_pghistory,
            patch.object(pghelpers, "pgh_core") as mock_pgh_core,
        ):
            mock_pgh_core.event_models.return_value = []
            apply_pghistory_tracks()

        assert mock_pghistory.track.call_count == 2
        mock_pghistory.track.assert_any_call("ev_a", exclude=["x"])
        mock_pghistory.track.assert_any_call("ev_b")
        # Each `track(...)` returns a decorator that's applied to the model.
        assert mock_pghistory.track.return_value.call_count == 2

    def test_skips_abstract_models(self):
        """`apply_pghistory_tracks` defensively skips models that became
        abstract after registration (registration itself rejects them, but
        the apply loop also guards)."""
        abstract_model = _make_model()
        pghistory_register_default_track(abstract_model, "ev")
        # Flip abstract after registration to simulate a post-registration mutation.
        abstract_model._meta.abstract = True

        with (
            patch.object(pghelpers, "pghistory") as mock_pghistory,
            patch.object(pghelpers, "pgh_core") as mock_pgh_core,
        ):
            mock_pgh_core.event_models.return_value = []
            apply_pghistory_tracks()

        mock_pghistory.track.assert_not_called()

    def test_skips_models_with_existing_event_models(self):
        """Idempotent: if pghistory already created event models for this
        target (e.g. earlier `apply_pghistory_tracks` call, or an external
        `@pghistory.track` decorator), don't re-register."""
        model = _make_model()
        pghistory_register_default_track(model, "ev")

        with (
            patch.object(pghelpers, "pghistory") as mock_pghistory,
            patch.object(pghelpers, "pgh_core") as mock_pgh_core,
        ):
            mock_pgh_core.event_models.return_value = ["already_tracked_event_model"]
            apply_pghistory_tracks()

        mock_pghistory.track.assert_not_called()

    def test_empty_registry_is_noop(self):
        with (
            patch.object(pghelpers, "pghistory") as mock_pghistory,
            patch.object(pghelpers, "pgh_core"),
        ):
            apply_pghistory_tracks()
        mock_pghistory.track.assert_not_called()


# ---------------------------------------------------------------------------
# pgtrigger_register_track / pgtrigger_register_default_track
# ---------------------------------------------------------------------------


def _make_trigger(name: str) -> pgtrigger.Trigger:
    """Real pgtrigger.Trigger so the registry's type checks pass."""
    return pgtrigger.Trigger(
        name=name,
        level=pgtrigger.Row,
        when=pgtrigger.After,
        operation=pgtrigger.Insert,
        func="RETURN NULL;",
    )


class TestPgtriggerRegister:
    @pytest.fixture(autouse=True)
    def _isolate(self):
        with patch.dict(_pgtrigger_registry, {}, clear=True):
            yield

    def test_default_track_records_triggers_marked_not_override(self):
        model = _make_model()
        triggers = [_make_trigger("t1"), _make_trigger("t2")]
        pgtrigger_register_default_track(model, triggers)

        stored, is_override = _pgtrigger_registry[model]
        assert stored == triggers
        assert is_override is False

    def test_default_track_coerces_iterable_to_list(self):
        """Passing a generator/tuple should still be stored as a list so
        callers reading the registry don't trip on exhausted iterators."""
        model = _make_model()
        t1 = _make_trigger("t1")
        pgtrigger_register_default_track(model, (t for t in [t1]))

        stored, _ = _pgtrigger_registry[model]
        assert stored == [t1]

    def test_default_track_returns_model(self):
        model = _make_model()
        assert pgtrigger_register_default_track(model, []) is model

    def test_default_track_raises_on_abstract_model(self):
        abstract = _make_model(abstract=True)
        with pytest.raises(ValueError, match="abstract models"):
            pgtrigger_register_default_track(abstract, [_make_trigger("t1")])
        assert abstract not in _pgtrigger_registry

    def test_decorator_track_marks_override_true(self):
        model = _make_model()
        t1 = _make_trigger("t1")
        result = pgtrigger_register_track(t1)(model)

        assert result is model
        stored, is_override = _pgtrigger_registry[model]
        assert stored == [t1]
        assert is_override is True

    def test_decorator_track_raises_on_abstract_model(self):
        abstract = _make_model(abstract=True)
        with pytest.raises(ValueError, match="abstract models"):
            pgtrigger_register_track(_make_trigger("t1"))(abstract)

    def test_decorator_overrides_existing_default(self):
        model = _make_model()
        default_t = _make_trigger("default_t")
        override_t = _make_trigger("override_t")
        pgtrigger_register_default_track(model, [default_t])
        pgtrigger_register_track(override_t)(model)

        stored, is_override = _pgtrigger_registry[model]
        assert stored == [override_t]
        assert is_override is True

    def test_default_does_not_overwrite_existing_decorator_override(self):
        model = _make_model()
        override_t = _make_trigger("override_t")
        default_t = _make_trigger("default_t")
        pgtrigger_register_track(override_t)(model)
        pgtrigger_register_default_track(model, [default_t])

        stored, is_override = _pgtrigger_registry[model]
        assert stored == [override_t]
        assert is_override is True


# ---------------------------------------------------------------------------
# apply_pgtrigger_tracks
# ---------------------------------------------------------------------------


class TestApplyPgtriggerTracks:
    @pytest.fixture(autouse=True)
    def _isolate(self):
        with patch.dict(_pgtrigger_registry, {}, clear=True):
            yield

    def test_registers_triggers_via_pgtrigger_api(self):
        """The helper must register through `pgtrigger.register` (not a raw
        `_meta.triggers.append`) so pgtrigger syncs `_meta.triggers`,
        `_meta.original_attrs["triggers"]` (read by the migration
        autodetector) and its own registry in one shot."""
        model = _make_model(triggers=[])
        t1 = _make_trigger("t1")
        t2 = _make_trigger("t2")
        pgtrigger_register_default_track(model, [t1, t2])

        with patch.object(pghelpers, "pgtrigger") as mock_pgtrigger:
            apply_pgtrigger_tracks()

        mock_pgtrigger.register.assert_called_once_with(t1, t2)
        mock_pgtrigger.register.return_value.assert_called_once_with(model)

    def test_handles_missing_triggers_attribute(self):
        """Some Django Meta objects don't have `triggers` until pgtrigger
        touches them — the helper must read it defensively and still
        register."""
        model = _make_model()  # No `triggers` attr set.
        t1 = _make_trigger("t1")
        pgtrigger_register_default_track(model, [t1])

        with patch.object(pghelpers, "pgtrigger") as mock_pgtrigger:
            apply_pgtrigger_tracks()  # must not raise

        mock_pgtrigger.register.assert_called_once_with(t1)
        mock_pgtrigger.register.return_value.assert_called_once_with(model)

    def test_skips_triggers_with_duplicate_names(self):
        """Idempotency guarantee — a trigger whose name already lives on
        `_meta.triggers` (e.g. one attached by DocumentIdMixin's
        `class_prepared` handler) must not be re-registered."""
        existing = _make_trigger("doc_id_insert")
        model = _make_model(triggers=[existing])

        replacement = _make_trigger("doc_id_insert")  # same name, different object
        new_trigger = _make_trigger("new_trigger")
        pgtrigger_register_default_track(model, [replacement, new_trigger])

        with patch.object(pghelpers, "pgtrigger") as mock_pgtrigger:
            apply_pgtrigger_tracks()

        # Only the non-duplicate trigger is registered; the duplicate-named
        # `replacement` is filtered out before reaching pgtrigger.
        mock_pgtrigger.register.assert_called_once_with(new_trigger)
        mock_pgtrigger.register.return_value.assert_called_once_with(model)

    def test_is_idempotent_across_multiple_calls(self):
        model = _make_model(triggers=[])
        t1 = _make_trigger("t1")
        pgtrigger_register_default_track(model, [t1])

        def fake_register(*triggers):
            # Mimic pgtrigger.register's side effect of syncing into
            # `_meta.triggers`, so the helper's dedup guard sees it next call.
            def decorator(m):
                for trigger in triggers:
                    if trigger not in m._meta.triggers:
                        m._meta.triggers.append(trigger)
                return m

            return decorator

        with patch.object(
            pghelpers.pgtrigger, "register", side_effect=fake_register
        ) as mock_register:
            apply_pgtrigger_tracks()
            apply_pgtrigger_tracks()
            apply_pgtrigger_tracks()

        # First call registers t1; the next two find it already on
        # `_meta.triggers` and skip it.
        mock_register.assert_called_once_with(t1)
        assert [t.name for t in model._meta.triggers] == ["t1"]

    def test_skips_abstract_models(self):
        abstract_model = _make_model(triggers=[])
        pgtrigger_register_default_track(abstract_model, [_make_trigger("t1")])
        # Flip after registration to bypass the register-time guard.
        abstract_model._meta.abstract = True

        apply_pgtrigger_tracks()

        assert abstract_model._meta.triggers == []

    def test_skips_swapped_models(self):
        """When the consuming project has swapped out a chat model, the
        abstract's default triggers should not bleed onto the swapped
        target (the project owns its own triggers)."""
        swapped_model = _make_model(swapped=True, triggers=[])
        pgtrigger_register_default_track(swapped_model, [_make_trigger("t1")])

        apply_pgtrigger_tracks()

        assert swapped_model._meta.triggers == []

    def test_empty_registry_is_noop(self):
        # Smoke test — just confirms no exception is raised.
        apply_pgtrigger_tracks()
