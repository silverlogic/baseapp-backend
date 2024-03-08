import graphene
from baseapp_auth.graphql.queries import UsersQueries
from graphene import relay


class Query(graphene.ObjectType, UsersQueries):
    node = relay.node.NodeField(relay.Node)


schema = graphene.Schema(query=Query)
