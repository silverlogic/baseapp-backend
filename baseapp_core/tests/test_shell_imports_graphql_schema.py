import pytest

from baseapp_core.graphql import decorators

from .factories import UserFactory

pytestmark = pytest.mark.django_db


def test_relay_id_triggers_schema_load():
    user = UserFactory()
    relay_id = user.relay_id

    assert decorators._graphql_loaded is True
    assert relay_id is not None
