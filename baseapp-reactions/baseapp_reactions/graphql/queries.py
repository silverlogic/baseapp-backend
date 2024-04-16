from baseapp_core.graphql import Node

from .object_types import ReactionObjectType


class ReactionsQueries:
    reaction = Node.Field(ReactionObjectType)
