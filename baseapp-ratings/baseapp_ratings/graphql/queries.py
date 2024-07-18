from baseapp_core.graphql import Node

from .object_types import RatingObjectType


class RatingsQueries:
    rate = Node.Field(RatingObjectType)
