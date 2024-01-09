from baseapp_core.graphql import Node

from .object_types import FollowNode


class FollowQuery:
    follow = Node.Field(FollowNode)
