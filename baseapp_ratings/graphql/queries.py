import swapper

from baseapp_core.graphql import Node, get_object_type_for_model

Rate = swapper.load_model("baseapp_ratings", "Rate")


class RatingsQueries:
    rate = Node.Field(get_object_type_for_model(Rate))
