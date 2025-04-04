import swapper

from baseapp_core.graphql import Node, get_object_type_for_model

Reaction = swapper.load_model("baseapp_reactions", "Reaction")


class ReactionsQueries:
    reaction = Node.Field(get_object_type_for_model(Reaction))
