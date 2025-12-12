import pytest

from baseapp_core.graphql import decorators

from .factories import UserFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def reset_graphql_loaded():
    """
    Automatically reset the GraphQL loaded flag before and after each test.
    """
    decorators._graphql_loaded = False
    yield
    decorators._graphql_loaded = False


def test_relay_id_triggers_schema_load():
    assert decorators._graphql_loaded is False

    user = UserFactory()
    relay_id = user.relay_id

    assert decorators._graphql_loaded is True
    assert relay_id is not None


def test_shell_behavior_triggers_schema_load(monkeypatch):
    assert decorators._graphql_loaded is False

    monkeypatch.setattr("sys.argv", ["manage.py", "shell"])

    user = UserFactory()
    relay_id = user.relay_id

    assert decorators._graphql_loaded is True
    assert relay_id is not None
    assert isinstance(relay_id, str)