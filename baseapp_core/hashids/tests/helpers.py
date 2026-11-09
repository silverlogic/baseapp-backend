from typing import Any
from unittest.mock import MagicMock

from baseapp_core.strawberry.relay import Node


def strawberry_info(instance: Any) -> MagicMock:
    """An `info` whose schema maps any type name to a Node type serving `instance`."""
    node_type = type(
        f"{type(instance).__name__}Type",
        (Node,),
        {
            "get_node": classmethod(lambda cls, info, pk: instance),
            "__strawberry_django_definition__": MagicMock(model=type(instance)),
        },
    )
    info = MagicMock()
    info.schema.get_type_by_name = MagicMock(return_value=MagicMock(origin=node_type))
    return info
