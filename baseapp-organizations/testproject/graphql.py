import graphene
from baseapp_auth.graphql.queries import UsersQueries
from baseapp_core.graphql import DeleteNode
from baseapp_profiles.graphql.mutations import ProfilesMutations
from baseapp_profiles.graphql.queries import ProfilesQueries
from graphene import relay

from baseapp_organizations.graphql.mutations import OrganizationsMutations
from baseapp_organizations.graphql.queries import OrganizationsQueries


class Query(graphene.ObjectType, ProfilesQueries, OrganizationsQueries, UsersQueries):
    node = relay.node.NodeField(relay.Node)


class Mutation(
    graphene.ObjectType,
    ProfilesMutations,
    OrganizationsMutations,
):
    delete_node = DeleteNode.Field()


schema = graphene.Schema(query=Query, mutation=Mutation)
