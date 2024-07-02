import graphene
from baseapp_auth.graphql.queries import UsersQueries
from baseapp_core.graphql import DeleteNode
from graphene import relay

from baseapp_profiles.graphql.mutations import ProfilesMutations
from baseapp_profiles.graphql.queries import ProfilesQueries


class Query(graphene.ObjectType, ProfilesQueries, UsersQueries):
    node = relay.node.NodeField(relay.Node)


class Mutation(
    graphene.ObjectType,
    ProfilesMutations,
):
    delete_node = DeleteNode.Field()


schema = graphene.Schema(query=Query, mutation=Mutation)
