import graphene
from baseapp_auth.graphql.queries import UsersQueries
from baseapp_core.graphql import DeleteNode
from baseapp_profiles.graphql import ProfilesQueries
from graphene import relay

from baseapp_reactions.graphql.mutations import ReactionsMutations
from baseapp_reactions.graphql.queries import ReactionsQueries


class Query(graphene.ObjectType, ReactionsQueries, UsersQueries, ProfilesQueries):
    node = relay.node.NodeField(relay.Node)


class Mutation(
    graphene.ObjectType,
    ReactionsMutations,
):
    delete_node = DeleteNode.Field()


schema = graphene.Schema(query=Query, mutation=Mutation)
