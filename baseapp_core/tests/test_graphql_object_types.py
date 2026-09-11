from unittest.mock import MagicMock

from baseapp_core.graphql.connections import CountedConnection
from baseapp_core.graphql.object_types import DjangoObjectTypeWithPkField


def test_counted_connection_resolve_edge_count() -> None:
    conn = CountedConnection.__new__(CountedConnection)
    conn.edges = [MagicMock(), MagicMock(), MagicMock()]
    assert conn.resolve_edge_count(info=None) == 3


def test_django_object_type_with_pk_field_resolve_pk() -> None:
    obj = DjangoObjectTypeWithPkField.__new__(DjangoObjectTypeWithPkField)
    obj.pk = 42
    assert obj.resolve_pk(info=None) == 42
