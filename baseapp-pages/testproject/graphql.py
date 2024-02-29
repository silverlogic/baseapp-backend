import graphene
from baseapp_core.graphql import DeleteNode
from graphene import relay

from baseapp_pages.graphql.mutations import PagesMutations
from baseapp_pages.graphql.queries import PagesQueries
from testproject.testapp.graphql.queries import UsersQuery


class Query(graphene.ObjectType, PagesQueries, UsersQuery):
    node = relay.node.NodeField(relay.Node)


class Mutation(
    graphene.ObjectType,
    PagesMutations,
):
    delete_node = DeleteNode.Field()


schema = graphene.Schema(query=Query, mutation=Mutation)
