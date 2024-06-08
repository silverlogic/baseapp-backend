from baseapp_core.graphql import Node

from .object_types import FollowObjectType


class FollowQuery:
    follow = Node.Field(FollowObjectType)
