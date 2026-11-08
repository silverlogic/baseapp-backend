import strawberry

from baseapp_core.strawberry.relay import typed_node_field

from .types import ReactionLazyType


@strawberry.type
class ReactionsQueries:
    reaction = typed_node_field(ReactionLazyType)
