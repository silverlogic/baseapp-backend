import strawberry

from baseapp_core.strawberry.relay import typed_node_field

from .types import RateLazyType


@strawberry.type
class RatingsQueries:
    rate = typed_node_field(RateLazyType)
