import swapper

from baseapp_core.graphql import Node, get_object_type_for_model

Follow = swapper.load_model("baseapp_follows", "Follow")


class FollowQuery:
    follow = Node.Field(get_object_type_for_model(Follow))
