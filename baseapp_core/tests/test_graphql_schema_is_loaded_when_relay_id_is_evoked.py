import pytest

from baseapp_core.graphql import decorators

from .factories import UserFactory

pytestmark = pytest.mark.django_db


def _reset_graphql_loaded():
    """
    Helper to reset the GraphQL loaded flag.
    """
    decorators._graphql_loaded = False


def test_relay_id_triggers_schema_load():
    _reset_graphql_loaded()
    assert decorators._graphql_loaded is False

    user = UserFactory()
    relay_id = user.relay_id

    assert decorators._graphql_loaded is True
    assert relay_id is not None


def test_relay_id_loads_schema_when_argv_looks_like_shell(monkeypatch):
    _reset_graphql_loaded()
    assert decorators._graphql_loaded is False

    monkeypatch.setattr("sys.argv", ["manage.py", "shell"])

    user = UserFactory()
    relay_id = user.relay_id

    assert decorators._graphql_loaded is True
    assert relay_id is not None
    assert isinstance(relay_id, str)
