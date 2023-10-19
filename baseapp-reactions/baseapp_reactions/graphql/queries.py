from baseapp_core.graphql import Node

from .object_types import ReactionNode


class ReactionsQuery:
    # TO DO: fix permission, follow target until its not a Comment anymore and check if request.user has permission to see
    reaction = Node.Field(ReactionNode)
