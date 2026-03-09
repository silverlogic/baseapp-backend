from baseapp_reactions.models import AbstractBaseReaction


class Reaction(AbstractBaseReaction):
    class Meta(AbstractBaseReaction.Meta):
        pass

    @classmethod
    def get_graphql_object_type(cls):
        from baseapp_reactions.graphql.object_types import ReactionObjectType

        return ReactionObjectType
