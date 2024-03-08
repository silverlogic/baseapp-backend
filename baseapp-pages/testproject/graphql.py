import graphene
from baseapp_auth.graphql.queries import UsersQueries
from baseapp_core.graphql import DeleteNode
from graphene import relay

from baseapp_pages.graphql.mutations import PagesMutations
from baseapp_pages.graphql.queries import PagesQueries


class Query(graphene.ObjectType, PagesQueries, UsersQueries):
    node = relay.node.NodeField(relay.Node)


class Mutation(
    graphene.ObjectType,
    PagesMutations,
):
    delete_node = DeleteNode.Field()


schema = graphene.Schema(query=Query, mutation=Mutation)
