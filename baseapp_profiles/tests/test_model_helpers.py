"""
Unit tests for the pure-Python helper functions and Func classes introduced
with the pgtrigger-based profile sync feature.

These functions are normally invoked during `makemigrations` (render) or at
class_prepared time (add_profilable_triggers), so they are not exercised by
the DB-level trigger tests.  The tests here call them directly.
"""

from unittest.mock import MagicMock

import pytest
import swapper
from django.contrib.auth import get_user_model

from baseapp_profiles.models import (
    CreateProfileFunc,
    ProfilableModel,
    UpdateProfileNameFunc,
    _columns_from_profile_name_sql,
    _python_default_to_sql,
    add_profilable_triggers,
)

User = get_user_model()
Profile = swapper.load_model("baseapp_profiles", "Profile")


# ---------------------------------------------------------------------------
# _python_default_to_sql
# ---------------------------------------------------------------------------


def test_python_default_to_sql_bool_true():
    assert _python_default_to_sql(True) == "TRUE"


def test_python_default_to_sql_bool_false():
    assert _python_default_to_sql(False) == "FALSE"


def test_python_default_to_sql_int():
    assert _python_default_to_sql(0) == "0"
    assert _python_default_to_sql(42) == "42"


def test_python_default_to_sql_float():
    assert _python_default_to_sql(1.5) == "1.5"


def test_python_default_to_sql_str():
    assert _python_default_to_sql("hello") == "'hello'"


def test_python_default_to_sql_str_escapes_single_quotes():
    assert _python_default_to_sql("it's") == "'it''s'"


def test_python_default_to_sql_dict():
    result = _python_default_to_sql({"total": 0})
    assert result == "'{\"total\":0}'::jsonb"


def test_python_default_to_sql_list():
    result = _python_default_to_sql([1, 2, 3])
    assert result == "'[1,2,3]'::jsonb"


def test_python_default_to_sql_dict_with_single_quotes():
    result = _python_default_to_sql({"key": "it's"})
    assert "it''s" in result
    assert result.endswith("::jsonb")


def test_python_default_to_sql_unsupported_type_returns_none():
    import datetime

    assert _python_default_to_sql(None) is None
    assert _python_default_to_sql(datetime.date.today()) is None
    assert _python_default_to_sql(object()) is None


# ---------------------------------------------------------------------------
# _columns_from_profile_name_sql
# ---------------------------------------------------------------------------


def test_columns_from_profile_name_sql_single_column():
    assert _columns_from_profile_name_sql("NEW.name") == ["name"]


def test_columns_from_profile_name_sql_multiple_columns():
    result = _columns_from_profile_name_sql("NEW.first_name || ' ' || NEW.last_name")
    assert result == ["first_name", "last_name"]


def test_columns_from_profile_name_sql_no_match_returns_none():
    assert _columns_from_profile_name_sql("SOME_FUNCTION()") is None
    assert _columns_from_profile_name_sql("OLD.name") is None


# ---------------------------------------------------------------------------
# UpdateProfileNameFunc.render()
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_update_profile_name_func_render_produces_valid_sql():
    func = UpdateProfileNameFunc(
        profile_name_sql="NEW.first_name || ' ' || NEW.last_name",
        profile_column="profile_id",
    )
    sql = func.render()
    assert "IF NEW.profile_id IS NOT NULL THEN" in sql
    assert "UPDATE" in sql
    assert "profiles_profile" in sql
    assert "TRIM(NEW.first_name || ' ' || NEW.last_name)" in sql


# ---------------------------------------------------------------------------
# CreateProfileFunc.render()
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_create_profile_func_render_produces_valid_sql():
    func = CreateProfileFunc(
        profile_name_sql="NEW.first_name || ' ' || NEW.last_name",
        profile_owner_sql="NEW.id",
        profile_column="profile_id",
        app_label="users",
        model_name="user",
        self_table="users_user",
        pk="id",
    )
    sql = func.render()
    assert "IF NEW.profile_id IS NULL THEN" in sql
    assert "ON CONFLICT (target_content_type_id, target_object_id)" in sql
    assert "RETURNING id" in sql
    assert "TRIM(NEW.first_name || ' ' || NEW.last_name)" in sql


@pytest.mark.django_db
def test_create_profile_func_render_raises_for_unconvertible_default(monkeypatch):
    """render() must fail fast when a NOT NULL field's default can't be serialised."""
    import datetime

    bad_field = MagicMock()
    bad_field.column = "problematic_col"
    bad_field.primary_key = False
    bad_field.null = False
    bad_field.has_default.return_value = True
    bad_field.get_default.return_value = datetime.datetime.now()
    type(bad_field).__name__ = "DateTimeField"

    # Extend the live field list with our unconvertible field.
    # monkeypatch replaces the attribute on the _meta instance for this test only.
    monkeypatch.setattr(Profile._meta, "fields", list(Profile._meta.fields) + [bad_field])

    func = CreateProfileFunc(
        profile_name_sql="NEW.first_name",
        profile_owner_sql="NEW.id",
        profile_column="profile_id",
        app_label="users",
        model_name="user",
        self_table="users_user",
        pk="id",
    )

    with pytest.raises(ValueError, match="problematic_col"):
        func.render()


# ---------------------------------------------------------------------------
# add_profilable_triggers guard branches
# ---------------------------------------------------------------------------


def test_add_profilable_triggers_skips_non_profilable_sender():
    """A class that does not inherit ProfilableModel is silently ignored."""

    class Unrelated:
        pass

    # Must not raise
    add_profilable_triggers(sender=Unrelated)


def test_add_profilable_triggers_skips_abstract_model():
    """Abstract ProfilableModel subclasses should not get triggers."""

    class FakeAbstract(ProfilableModel):
        profile_name_sql = "NEW.name"

        class Meta:
            abstract = True
            app_label = "baseapp_profiles"

    original = list(getattr(FakeAbstract._meta, "triggers", []))
    add_profilable_triggers(sender=FakeAbstract)
    assert getattr(FakeAbstract._meta, "triggers", original) == original


def test_add_profilable_triggers_skips_when_no_profile_name_sql():
    """ProfilableModel subclass without profile_name_sql is ignored."""

    class FakeNoSql(ProfilableModel):
        profile_name_sql = None

        class Meta:
            abstract = True
            app_label = "baseapp_profiles"

    add_profilable_triggers(sender=FakeNoSql)
    assert not any(
        t.name == "update_profile_name" for t in getattr(FakeNoSql._meta, "triggers", [])
    )


def test_add_profilable_triggers_skips_duplicate_trigger():
    """Calling add_profilable_triggers twice must not add the same trigger twice."""
    trigger_names_before = [t.name for t in getattr(User._meta, "triggers", [])]
    count_before = trigger_names_before.count("update_profile_name")

    add_profilable_triggers(sender=User)

    trigger_names_after = [t.name for t in getattr(User._meta, "triggers", [])]
    assert trigger_names_after.count("update_profile_name") == count_before
